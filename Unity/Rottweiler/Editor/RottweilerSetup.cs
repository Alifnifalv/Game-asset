// Rottweiler (male) asset setup for Unity (Editor only). Adapted from Unity/Calf/Editor/CalfSetup.cs (same importer,
// material and prefab code; the Rottweiler's clip table, gait speeds and Animator states).
// Menu: Tools > Rottweiler > Setup Rottweiler Asset
//
// Put the whole Unity/Rottweiler folder anywhere under Assets/. The script finds Rottweiler.fbx next to it and:
//   1. configures the model importer: Generic rig, Rig tab > Root node = the "Root" bone (the Avatar's root-motion bone),
//      imported tangents, bones kept, per-clip loop and Root Transform bake settings
//   2. configures texture importers (normal map type, linear data maps, 4K)
//   3. creates materials for the active render pipeline (URP Lit / HDRP Lit / Built-in Standard) and remaps the FBX
//      materials (short coat: no shell fur)
//   4. creates Rottweiler.controller, or rebuilds it in place: Idle state, Speed (m/s) blend tree over the root-motion
//      gaits, sit / lie chains, looping behaviour states (sniff, eat, growl, pant), one-shots, and death
//   5. saves Rottweiler.prefab (a variant of the model) with the Animator (root motion on) and the LODGroup thresholds
// Running it again is safe: materials, controller and prefab keep their asset GUIDs (hand edits to the controller and
// the prefab are replaced).
//
// NOTE: written without access to a Unity editor in the build environment. It compiles (C# 9) against stubs of the
// Unity 2021.3+ / 6 APIs it uses; the import itself still needs one check in Unity (see README "Not verified").
#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using UnityEngine.Rendering;

namespace RottweilerAsset.EditorTools
{
    public static class RottweilerSetup
    {
        const string RootBone = "Root";

        // clip name -> (loop, root motion kind). Rottweiler_export_manifest.json (next to the FBX) wins for the loop flag and
        // fills in takes this table does not know; a mismatch is logged.
        enum RootMotion { None, Translate, TranslateAndTurn, Turn }
        static readonly Dictionary<string, (bool loop, RootMotion rm)> ClipSpec = new Dictionary<string, (bool, RootMotion)>
        {
            { "Idle", (true, RootMotion.None) }, { "Idle_Pant", (true, RootMotion.None) }, { "Idle_LookAround", (true, RootMotion.None) },
            { "Idle_Sniff", (true, RootMotion.None) }, { "Eat", (true, RootMotion.None) }, { "Growl", (true, RootMotion.None) },
            { "Bark", (false, RootMotion.None) }, { "Attack", (false, RootMotion.None) }, { "PlayBow", (false, RootMotion.None) },
            { "Walk_Slow", (true, RootMotion.None) }, { "Walk", (true, RootMotion.None) }, { "Trot", (true, RootMotion.None) },
            { "Gallop", (true, RootMotion.None) },
            { "Walk_Slow_RM", (true, RootMotion.Translate) }, { "Walk_RM", (true, RootMotion.Translate) },
            { "Trot_RM", (true, RootMotion.Translate) }, { "Gallop_RM", (true, RootMotion.Translate) },
            { "Sit_Start", (false, RootMotion.None) }, { "Sit_Idle", (true, RootMotion.None) }, { "Sit_End", (false, RootMotion.None) },
            { "Lie_Start", (false, RootMotion.None) }, { "Lying_Idle", (true, RootMotion.None) }, { "Lie_End", (false, RootMotion.None) },
            { "Jump", (false, RootMotion.Translate) }, { "Death", (false, RootMotion.None) },
        };

        // Speed blend tree children and their root speeds in m/s (export values; the thresholds use the root speed Unity
        // measures on the imported clip, and a difference of more than 10% is logged). Idle is its own state, not a child.
        // timeScale != 1 adds a time-scaled copy of a gait: Trot_RM x1.4 (= 3.5 m/s) and Gallop_RM x0.6 (= 3.9 m/s)
        // confine the Trot/Gallop crossfade to 3.5-3.9 m/s (the two gaits have different footfalls: a wide crossfade
        // crosses the legs; the calf's review A1).
        static readonly (string clip, float speed, float timeScale)[] Locomotion =
        {
            ("Walk_Slow_RM", 0.55f, 1f), ("Walk_RM", 1.15f, 1f), ("Trot_RM", 2.5f, 1f),
            ("Trot_RM", 2.5f, 1.4f), ("Gallop_RM", 6.5f, 0.6f), ("Gallop_RM", 6.5f, 1f)
        };
        const float SpeedStart = 0.1f, SpeedStop = 0.05f;     // Idle -> Locomotion above 0.1 m/s, back below 0.05 m/s

        // one-shots: played once from Idle / Locomotion, then back to Locomotion (Speed > 0.1) or Idle
        static readonly (string clip, string trigger)[] OneShots =
        {
            ("Bark", "Bark"), ("Attack", "Attack"), ("PlayBow", "PlayBow"), ("Jump", "Jump"), ("Idle_LookAround", "LookAround")
        };
        // looping behaviours entered from Idle while their bool is set (blended in and out: they start and end on
        // poses close to Idle; the paws never move)
        static readonly (string clip, string flag)[] Behaviours =
        {
            ("Idle_Sniff", "Sniff"), ("Eat", "Eat"), ("Growl", "Growl"), ("Idle_Pant", "Pant")
        };
        const string ReadyTag = "Ready", DeadTag = "Dead";   // state tags for game code (Animator.GetCurrentAnimatorStateInfo(0).IsTag)

        [MenuItem("Tools/Rottweiler/Setup Rottweiler Asset")]
        public static void Setup()
        {
            string fbx = FindFbx();
            if (fbx == null) { EditorUtility.DisplayDialog("Rottweiler setup", "Rottweiler.fbx not found under Assets/.", "OK"); return; }
            string dir = Path.GetDirectoryName(fbx).Replace('\\', '/');
            try
            {
                AssetDatabase.StartAssetEditing();
                ConfigureTextures(dir);
            }
            finally { AssetDatabase.StopAssetEditing(); }
            AssetDatabase.Refresh();

            var mats = CreateMaterials(dir);
            ConfigureModel(fbx, dir, mats);
            var ctrl = CreateController(dir, fbx);
            var prefab = CreatePrefab(dir, fbx, ctrl);
            Selection.activeObject = prefab;
            Debug.Log($"[Rottweiler] setup complete: {AssetDatabase.GetAssetPath(prefab)} (pipeline: {PipelineName()})");
        }

        // ------------------------------------------------------------------ discovery
        static string FindFbx()
        {
            return AssetDatabase.FindAssets("Rottweiler t:Model")
                .Select(AssetDatabase.GUIDToAssetPath)
                .FirstOrDefault(p => Path.GetFileName(p).Equals("Rottweiler.fbx", StringComparison.OrdinalIgnoreCase));
        }

        static string CleanClipName(string take)
        {
            int i = take.LastIndexOf('|');           // Blender takes may be named "Armature|Action"
            return i >= 0 ? take.Substring(i + 1) : take;
        }

        static string PipelineName()
        {
            var rp = GraphicsSettings.currentRenderPipeline;
            if (rp == null) return "Built-in";
            string t = rp.GetType().Name;
            if (t.Contains("Universal")) return "URP";
            if (t.Contains("HDRenderPipeline")) return "HDRP";
            return t;
        }

        // ------------------------------------------------------------------ textures
        static void ConfigureTextures(string dir)
        {
            foreach (string guid in AssetDatabase.FindAssets("t:Texture2D", new[] { dir }))
            {
                string p = AssetDatabase.GUIDToAssetPath(guid);
                var ti = AssetImporter.GetAtPath(p) as TextureImporter;
                if (ti == null) continue;
                string n = Path.GetFileNameWithoutExtension(p);
                bool normal = n.EndsWith("_Normal");
                bool color = n.EndsWith("_BaseColor");
                // Default type for every data map, AO included: URP / Built-in Lit read occlusion from G, which a
                // single-channel (R8 / BC4) import would leave at 0
                ti.textureType = normal ? TextureImporterType.NormalMap : TextureImporterType.Default;
                ti.sRGBTexture = color;                       // data maps (mask, roughness, AO, fur mask/noise, normal) are linear
                ti.maxTextureSize = 4096;
                ti.mipmapEnabled = true;
                ti.alphaIsTransparency = false;
                ti.textureCompression = TextureImporterCompression.CompressedHQ;
                ti.SaveAndReimport();
            }
        }

        static Texture2D Tex(string dir, string name)
        {
            string guid = AssetDatabase.FindAssets(name + " t:Texture2D", new[] { dir })
                .FirstOrDefault(g => Path.GetFileNameWithoutExtension(AssetDatabase.GUIDToAssetPath(g)) == name);
            return guid == null ? null : AssetDatabase.LoadAssetAtPath<Texture2D>(AssetDatabase.GUIDToAssetPath(guid));
        }

        // ------------------------------------------------------------------ materials
        static Dictionary<string, Material> CreateMaterials(string dir)
        {
            string mdir = dir + "/Materials";
            if (!AssetDatabase.IsValidFolder(mdir)) AssetDatabase.CreateFolder(dir, "Materials");
            string pipe = PipelineName();
            var result = new Dictionary<string, Material>();

            var baseColor = Tex(dir, "T_Rottweiler_BaseColor");
            var normal = Tex(dir, "T_Rottweiler_Normal");
            var urpMS = Tex(dir, "T_Rottweiler_MetallicSmoothness");
            var hdrpMask = Tex(dir, "T_Rottweiler_MaskMap");
            var ao = Tex(dir, "T_Rottweiler_AO");
            var eye = Tex(dir, "T_RottweilerEye_BaseColor");

            result["M_Rottweiler_Body"] = MakeLit(mdir + "/M_Rottweiler_Body.mat", pipe, baseColor, normal, urpMS, hdrpMask, ao, 1.0f);
            result["M_Rottweiler_Eye"] = MakeLit(mdir + "/M_Rottweiler_Eye.mat", pipe, eye, null, null, null, null, 0.92f);
            AssetDatabase.SaveAssets();
            return result;
        }

        static Material MakeLit(string path, string pipe, Texture2D albedo, Texture2D normal, Texture2D metallicSmooth,
                                Texture2D mask, Texture2D occlusion, float smoothness)
        {
            string shaderName = pipe == "URP" ? "Universal Render Pipeline/Lit" : pipe == "HDRP" ? "HDRP/Lit" : "Standard";
            var shader = Shader.Find(shaderName);
            if (shader == null) { Debug.LogError($"[Rottweiler] shader {shaderName} not found"); shader = Shader.Find("Standard"); }
            var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null) { mat = new Material(shader); AssetDatabase.CreateAsset(mat, path); }
            else mat.shader = shader;

            if (pipe == "URP")
            {
                if (albedo) mat.SetTexture("_BaseMap", albedo);
                mat.SetColor("_BaseColor", Color.white);
                if (normal) { mat.SetTexture("_BumpMap", normal); mat.SetFloat("_BumpScale", 1f); mat.EnableKeyword("_NORMALMAP"); }
                mat.SetFloat("_Metallic", 0f);
                if (metallicSmooth)
                {
                    mat.SetTexture("_MetallicGlossMap", metallicSmooth); mat.EnableKeyword("_METALLICSPECGLOSSMAP");
                    mat.SetFloat("_SmoothnessTextureChannel", 0f);   // smoothness from the metallic map alpha
                    mat.SetFloat("_Smoothness", 1f);
                }
                else mat.SetFloat("_Smoothness", smoothness);
                if (occlusion) { mat.SetTexture("_OcclusionMap", occlusion); mat.SetFloat("_OcclusionStrength", 1f); mat.EnableKeyword("_OCCLUSIONMAP"); }
            }
            else if (pipe == "HDRP")
            {
                if (albedo) mat.SetTexture("_BaseColorMap", albedo);
                mat.SetColor("_BaseColor", Color.white);
                if (normal) { mat.SetTexture("_NormalMap", normal); mat.SetFloat("_NormalScale", 1f); mat.EnableKeyword("_NORMALMAP"); mat.EnableKeyword("_NORMALMAP_TANGENT_SPACE"); }
                if (mask)
                {
                    mat.SetTexture("_MaskMap", mask); mat.EnableKeyword("_MASKMAP");
                    mat.SetFloat("_SmoothnessRemapMin", 0f); mat.SetFloat("_SmoothnessRemapMax", 1f);
                    mat.SetFloat("_AORemapMin", 0f); mat.SetFloat("_AORemapMax", 1f);
                    mat.SetFloat("_MetallicRemapMin", 0f); mat.SetFloat("_MetallicRemapMax", 0f);
                }
                else { mat.SetFloat("_Smoothness", smoothness); mat.SetFloat("_Metallic", 0f); }
                // let HDRP rebuild keywords/passes if its editor assembly is present (reflection: no hard HDRP dependency)
                var t = Type.GetType("UnityEditor.Rendering.HighDefinition.HDShaderUtils, Unity.RenderPipelines.HighDefinition.Editor");
                var m = t?.GetMethod("ResetMaterialKeywords", new[] { typeof(Material) });
                m?.Invoke(null, new object[] { mat });
            }
            else
            {
                if (albedo) mat.SetTexture("_MainTex", albedo);
                if (normal) { mat.SetTexture("_BumpMap", normal); mat.EnableKeyword("_NORMALMAP"); }
                mat.SetFloat("_Metallic", 0f);
                if (metallicSmooth)
                {
                    mat.SetTexture("_MetallicGlossMap", metallicSmooth); mat.EnableKeyword("_METALLICGLOSSMAP");
                    mat.SetFloat("_GlossMapScale", 1f);
                }
                else mat.SetFloat("_Glossiness", smoothness);
                if (occlusion) mat.SetTexture("_OcclusionMap", occlusion);
            }
            EditorUtility.SetDirty(mat);
            return mat;
        }

        // ------------------------------------------------------------------ model importer
        [Serializable] class ManifestTake { public string name = ""; public bool cyclic = false; public bool root_motion = false; }
        [Serializable] class Manifest { public ManifestTake[] takes = new ManifestTake[0]; }

        static Dictionary<string, ManifestTake> LoadManifest(string dir)
        {
            var result = new Dictionary<string, ManifestTake>();
            var json = AssetDatabase.LoadAssetAtPath<TextAsset>(dir + "/Rottweiler_export_manifest.json");
            if (json == null) return result;
            try
            {
                var m = JsonUtility.FromJson<Manifest>(json.text);
                if (m?.takes != null)
                    foreach (var t in m.takes) if (!string.IsNullOrEmpty(t.name)) result[t.name] = t;
            }
            catch (ArgumentException e) { Debug.LogWarning($"[Rottweiler] could not read Rottweiler_export_manifest.json ({e.Message}); using the clip table"); }
            return result;
        }

        static void ConfigureModel(string fbx, string dir, Dictionary<string, Material> mats)
        {
            var mi = (ModelImporter)AssetImporter.GetAtPath(fbx);
            mi.globalScale = 1f;
            mi.useFileScale = true;
            mi.importBlendShapes = false;
            mi.importCameras = false;
            mi.importLights = false;
            mi.importNormals = ModelImporterNormals.Import;
            mi.importTangents = ModelImporterTangents.Import;      // exported tangents = the normal-map bake basis (exact)
            mi.optimizeBones = false;                              // "Strip Bones" off: Root (the root-motion bone) carries no weights
            mi.animationType = ModelImporterAnimationType.Generic;
            mi.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            mi.importAnimation = true;
            mi.animationCompression = ModelImporterAnimationCompression.Optimal;
            // Animation tab > Motion > Root Motion Node = <None>. A motion node would override (and hide) the per-clip
            // Root Transform settings below; root motion comes from the Avatar's root node instead.
            mi.motionNodeName = "";
            mi.materialImportMode = ModelImporterMaterialImportMode.ImportViaMaterialDescription;
            foreach (var kv in mats)
                mi.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), kv.Key), kv.Value);
            SetRootMotionBone(mi, RootBone);
            mi.SaveAndReimport();

            var model = AssetDatabase.LoadAssetAtPath<GameObject>(fbx);
            if (!model.GetComponentsInChildren<Transform>(true).Any(t => t.name == RootBone))
                Debug.LogWarning($"[Rottweiler] bone '{RootBone}' not found; set Rig > Root node by hand");

            var manifest = LoadManifest(dir);
            var clips = new List<ModelImporterClipAnimation>();
            foreach (var c in mi.defaultClipAnimations)
            {
                string name = CleanClipName(c.takeName);
                c.name = name;
                bool known = ClipSpec.TryGetValue(name, out var spec);
                if (manifest.TryGetValue(name, out var take))
                {
                    if (known && (take.cyclic != spec.loop || take.root_motion != (spec.rm != RootMotion.None)))
                        Debug.LogWarning($"[Rottweiler] {name}: manifest says loop={take.cyclic} root_motion={take.root_motion}; using the manifest");
                    spec.loop = take.cyclic;
                    if (!take.root_motion) spec.rm = RootMotion.None;
                    else if (!known || spec.rm == RootMotion.None) spec.rm = RootMotion.TranslateAndTurn;
                }
                else if (!known) Debug.LogWarning($"[Rottweiler] take {name}: not in the clip table or the manifest; imported as an in-place one-shot");
                c.loopTime = spec.loop;
                c.loopPose = false;                 // clips are authored with an exact seam (first frame == last frame)
                bool translates = spec.rm == RootMotion.Translate || spec.rm == RootMotion.TranslateAndTurn;
                bool turns = spec.rm == RootMotion.Turn || spec.rm == RootMotion.TranslateAndTurn;
                c.lockRootRotation = !turns;        // "Bake Into Pose" when the clip does not turn the root
                c.keepOriginalOrientation = true;
                c.lockRootHeightY = true;           // body height stays in the pose (root never moves vertically)
                c.keepOriginalPositionY = true;
                c.lockRootPositionXZ = !translates;
                c.keepOriginalPositionXZ = true;
                clips.Add(c);
            }
            mi.clipAnimations = clips.ToArray();
            mi.SaveAndReimport();
        }

        // Rig tab > Root node: the Avatar's root-motion bone, to which the per-clip Root Transform settings apply.
        // HumanDescription.m_RootMotionBoneName is internal, so set it through the serialized importer the way
        // ModelImporterRigEditor does (it stores the bone NAME, not the path). Call after the C# property changes.
        static void SetRootMotionBone(ModelImporter mi, string bone)
        {
            var so = new SerializedObject(mi);
            var p = so.FindProperty("m_HumanDescription.m_RootMotionBoneName");
            if (p == null) { Debug.LogWarning($"[Rottweiler] could not set Rig > Root node; set it to '{bone}' by hand"); return; }
            p.stringValue = bone;
            so.ApplyModifiedPropertiesWithoutUndo();
        }

        static AnimationClip Clip(string fbx, string name)
        {
            return AssetDatabase.LoadAllAssetsAtPath(fbx).OfType<AnimationClip>()
                .FirstOrDefault(c => !c.name.StartsWith("__preview__") && c.name == name);
        }

        // Root speed Unity measured on the imported clip: the blend-tree threshold, and a check of the root-motion setup
        static float RootSpeed(AnimationClip c, float expected)
        {
            float v = c.averageSpeed.magnitude;
            if (v < 0.05f)
            {
                Debug.LogWarning($"[Rottweiler] {c.name}: no root motion in Unity ({v:F3} m/s); check Rig > Root node = {RootBone}. Threshold {expected} m/s");
                return expected;
            }
            if (Mathf.Abs(v - expected) > 0.1f * expected)
                Debug.LogWarning($"[Rottweiler] {c.name}: root speed {v:F3} m/s in Unity, {expected} m/s in the export");
            else Debug.Log($"[Rottweiler] {c.name}: root speed {v:F3} m/s (export {expected} m/s)");
            return v;
        }

        // ------------------------------------------------------------------ animator controller
        // Rebuild in place when the controller exists, so its GUID (and every prefab, scene or Animator Override
        // Controller that references it) survives. Hand edits are replaced.
        static AnimatorController LoadOrResetController(string path)
        {
            var ctrl = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
            if (ctrl == null)
            {
                AssetDatabase.DeleteAsset(path);                 // something that is not a controller (no-op if nothing is there)
                return AnimatorController.CreateAnimatorControllerAtPath(path);
            }
            ctrl.layers = new AnimatorControllerLayer[0];
            ctrl.parameters = new AnimatorControllerParameter[0];
            foreach (var o in AssetDatabase.LoadAllAssetsAtPath(path))
                if (o != null && o != ctrl) UnityEngine.Object.DestroyImmediate(o, true);   // old state machines, states, transitions, blend trees
            ctrl.AddLayer("Base Layer");
            EditorUtility.SetDirty(ctrl);
            return ctrl;
        }

        static AnimatorController CreateController(string dir, string fbx)
        {
            string path = dir + "/Rottweiler.controller";
            var ctrl = LoadOrResetController(path);
            ctrl.AddParameter("Speed", AnimatorControllerParameterType.Float);
            foreach (var b in new[] { "Sit", "Lie" }.Concat(Behaviours.Select(x => x.flag)))
                ctrl.AddParameter(b, AnimatorControllerParameterType.Bool);
            foreach (var t in OneShots.Select(o => o.trigger).Concat(new[] { "Die" }))
                ctrl.AddParameter(t, AnimatorControllerParameterType.Trigger);
            var sm = ctrl.layers[0].stateMachine;

            AnimatorState State(string clip, float x, float y, string tag = "")
            {
                var c = Clip(fbx, clip);
                if (!c) { Debug.LogWarning($"[Rottweiler] clip {clip} missing"); return null; }
                var s = sm.AddState(clip, new Vector3(x, y)); s.motion = c; s.tag = tag; return s;
            }
            AnimatorStateTransition Go(AnimatorState a, AnimatorState b, float dur, bool exit, float exitTime = 1f)
            {
                if (a == null || b == null) return null;
                var t = a.AddTransition(b); t.duration = dur; t.hasExitTime = exit; if (exit) t.exitTime = exitTime; return t;
            }

            var idle = State("Idle", 250, 0, ReadyTag);
            if (idle == null) { idle = sm.AddState("Idle", new Vector3(250, 0)); idle.tag = ReadyTag; }
            sm.defaultState = idle;

            // Locomotion: Speed (m/s) blend tree over the root-motion gaits
            var tree = new BlendTree { name = "Locomotion", blendType = BlendTreeType.Simple1D, blendParameter = "Speed", useAutomaticThresholds = false };
            AssetDatabase.AddObjectToAsset(tree, ctrl);
            var loco = sm.AddState("Locomotion", new Vector3(250, 160));
            loco.motion = tree; loco.tag = ReadyTag;
            foreach (var (clip, speed, timeScale) in Locomotion)
            {
                var c = Clip(fbx, clip);
                if (c)
                {
                    tree.AddChild(c, RootSpeed(c, speed) * timeScale);
                    if (timeScale != 1f)
                    {
                        var ch = tree.children;                   // ChildMotion is a struct: edit the copy, assign it back
                        ch[ch.Length - 1].timeScale = timeScale;
                        tree.children = ch;
                    }
                }
                else Debug.LogWarning($"[Rottweiler] clip {clip} missing for locomotion");
            }
            Go(idle, loco, 0.25f, false)?.AddCondition(AnimatorConditionMode.Greater, SpeedStart, "Speed");
            Go(loco, idle, 0.25f, false)?.AddCondition(AnimatorConditionMode.Less, SpeedStop, "Speed");

            var ready = new[] { idle, loco };
            void Enter(AnimatorState s, float dur, AnimatorConditionMode mode, string param)
            {
                foreach (var r in ready) Go(r, s, dur, false)?.AddCondition(mode, 0, param);
            }
            void Leave(AnimatorState s, float dur, float exitTime)
            {
                Go(s, loco, dur, true, exitTime)?.AddCondition(AnimatorConditionMode.Greater, SpeedStart, "Speed");
                Go(s, idle, dur, true, exitTime);
            }
            var standing = new List<AnimatorState> { idle, loco };   // states Death may start from

            // sitting: Sit_Start -> Sit_Idle (while Sit) -> Sit_End
            var sS = State("Sit_Start", 550, -300); var sI = State("Sit_Idle", 800, -300); var sE = State("Sit_End", 1050, -300);
            Enter(sS, 0.2f, AnimatorConditionMode.If, "Sit");
            Go(sS, sI, 0.05f, true, 0.98f);
            Go(sI, sE, 0.15f, false)?.AddCondition(AnimatorConditionMode.IfNot, 0, "Sit");
            Leave(sE, 0.2f, 0.95f);
            // lying: Lie_Start -> Lying_Idle (while Lie) -> Lie_End
            var lS = State("Lie_Start", 550, -180); var lI = State("Lying_Idle", 800, -180); var lE = State("Lie_End", 1050, -180);
            Enter(lS, 0.2f, AnimatorConditionMode.If, "Lie");
            Go(lS, lI, 0.05f, true, 0.98f);
            Go(lI, lE, 0.2f, false)?.AddCondition(AnimatorConditionMode.IfNot, 0, "Lie");
            Leave(lE, 0.2f, 0.95f);
            standing.AddRange(new[] { sS, sI, sE, lS, lI, lE });

            // looping behaviours: from Idle while the bool is set, back to Idle when it clears
            float by = -420;
            foreach (var (clip, flag) in Behaviours)
            {
                var s = State(clip, 250 - 300, by += 70);
                if (s == null) continue;
                Go(idle, s, 0.3f, false)?.AddCondition(AnimatorConditionMode.If, 0, flag);
                Go(s, idle, 0.3f, false)?.AddCondition(AnimatorConditionMode.IfNot, 0, flag);
                Go(s, loco, 0.25f, false)?.AddCondition(AnimatorConditionMode.Greater, SpeedStart, "Speed");
                standing.Add(s);
            }

            // one-shots
            float y = -60;
            foreach (var (clip, trig) in OneShots)
            {
                var s = State(clip, 550, y += 60);
                Enter(s, 0.2f, AnimatorConditionMode.If, trig);
                Leave(s, 0.2f, 0.95f);
                if (clip != "Jump") standing.Add(s);              // no death in mid-air: Die waits for the landing
            }

            // death from every standing state (the clip starts from the standing pose), checked before other transitions
            var death = State("Death", 900, 200, DeadTag);
            if (death != null)
                foreach (var s in standing.Where(s => s != null))
                {
                    Go(s, death, 0.25f, false).AddCondition(AnimatorConditionMode.If, 0, "Die");
                    s.transitions = s.transitions.OrderBy(t => t.destinationState == death ? 0 : 1).ToArray();
                }
            EditorUtility.SetDirty(ctrl);
            AssetDatabase.SaveAssets();
            return ctrl;
        }

        // ------------------------------------------------------------------ prefab
        static GameObject CreatePrefab(string dir, string fbx, AnimatorController ctrl)
        {
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(fbx);
            var inst = (GameObject)PrefabUtility.InstantiatePrefab(model);
            inst.name = "Rottweiler";
            var animator = inst.GetComponent<Animator>();
            if (animator == null) animator = inst.AddComponent<Animator>();   // Unity null check (no ?? on UnityEngine.Object)
            animator.runtimeAnimatorController = ctrl;
            animator.applyRootMotion = true;
            animator.cullingMode = AnimatorCullingMode.CullUpdateTransforms;

            // The importer usually creates the LODGroup from the _LOD0.._LOD2 names; apply the documented thresholds either way
            var rs = inst.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            Renderer[] Lod(int i) => rs.Where(r => r.name.EndsWith("_LOD" + i)).Cast<Renderer>().ToArray();
            var lg = inst.GetComponent<LODGroup>();
            if (lg == null) lg = inst.AddComponent<LODGroup>();
            lg.SetLODs(new[] { new LOD(0.35f, Lod(0)), new LOD(0.12f, Lod(1)), new LOD(0.02f, Lod(2)) });
            lg.RecalculateBounds();
            for (int i = 0; i < 3; i++) if (Lod(i).Length == 0) Debug.LogWarning($"[Rottweiler] no renderer named *_LOD{i}");
            foreach (var smr in rs)
                smr.updateWhenOffscreen = false;

            string path = dir + "/Rottweiler.prefab";
            var prefab = PrefabUtility.SaveAsPrefabAsset(inst, path);
            UnityEngine.Object.DestroyImmediate(inst);
            return prefab;
        }
    }
}
#endif
