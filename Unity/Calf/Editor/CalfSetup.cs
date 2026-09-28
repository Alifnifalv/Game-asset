// Calf asset setup for Unity (Editor only).
// Menu: Tools > Calf > Setup Calf Asset
//
// Put the whole Unity/Calf folder anywhere under Assets/ (e.g. Assets/Calf). The script finds Calf.fbx next to it and:
//   1. configures the model importer (Generic rig, Root as motion node, MikkTSpace tangents, per-clip loop/root-motion settings)
//   2. configures texture importers (normal map type, linear data maps, 4K)
//   3. creates materials for the active render pipeline (URP Lit / HDRP Lit / Built-in Standard) and remaps the FBX materials
//   4. creates an Animator Controller (Speed blend tree + graze / lie / call / leap / shake / eat / turn / death states)
//   5. saves a prefab (Calf.prefab) with Animator (root motion on) and a LODGroup
//
// NOTE: written without access to a Unity editor in the build environment; verified against the documented Unity 2021.3+/6 APIs.
#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using UnityEngine.Rendering;

namespace CalfAsset.EditorTools
{
    public static class CalfSetup
    {
        // clip name -> (loop, root motion kind)
        enum RootMotion { None, Translate, TranslateAndTurn, Turn }
        static readonly Dictionary<string, (bool loop, RootMotion rm)> ClipSpec = new Dictionary<string, (bool, RootMotion)>
        {
            { "Idle", (true, RootMotion.None) }, { "Idle_LookAround", (true, RootMotion.None) }, { "Eating", (true, RootMotion.None) },
            { "Walk", (true, RootMotion.None) }, { "Trot", (true, RootMotion.None) }, { "Gallop", (true, RootMotion.None) },
            { "Walk_RM", (true, RootMotion.Translate) }, { "Trot_RM", (true, RootMotion.Translate) }, { "Gallop_RM", (true, RootMotion.Translate) },
            { "TurnLeft90", (false, RootMotion.Turn) }, { "TurnRight90", (false, RootMotion.Turn) },
            { "Graze_Start", (false, RootMotion.None) }, { "Graze_Loop", (true, RootMotion.None) }, { "Graze_End", (false, RootMotion.None) },
            { "Call", (false, RootMotion.None) }, { "HeadShake", (false, RootMotion.None) },
            { "LieDown", (false, RootMotion.None) }, { "Lying_Idle", (true, RootMotion.None) }, { "GetUp", (false, RootMotion.None) },
            { "Death", (false, RootMotion.None) }, { "Leap", (false, RootMotion.Translate) },
        };

        // locomotion blend thresholds (m/s) = clip root speeds from tools/anim_gait.py
        static readonly (string clip, float speed)[] Locomotion =
        {
            ("Idle", 0f), ("Walk_RM", 0.93f), ("Trot_RM", 2.34f), ("Gallop_RM", 4.39f)
        };

        [MenuItem("Tools/Calf/Setup Calf Asset")]
        public static void Setup()
        {
            string fbx = FindFbx();
            if (fbx == null) { EditorUtility.DisplayDialog("Calf setup", "Calf.fbx not found under Assets/.", "OK"); return; }
            string dir = Path.GetDirectoryName(fbx).Replace('\\', '/');
            try
            {
                AssetDatabase.StartAssetEditing();
                ConfigureTextures(dir);
            }
            finally { AssetDatabase.StopAssetEditing(); }
            AssetDatabase.Refresh();

            var mats = CreateMaterials(dir);
            ConfigureModel(fbx, mats);
            var ctrl = CreateController(dir, fbx);
            var prefab = CreatePrefab(dir, fbx, ctrl);
            Selection.activeObject = prefab;
            Debug.Log($"[Calf] setup complete: {AssetDatabase.GetAssetPath(prefab)} (pipeline: {PipelineName()})");
        }

        // ------------------------------------------------------------------ discovery
        static string FindFbx()
        {
            return AssetDatabase.FindAssets("Calf t:Model")
                .Select(AssetDatabase.GUIDToAssetPath)
                .FirstOrDefault(p => Path.GetFileName(p).Equals("Calf.fbx", StringComparison.OrdinalIgnoreCase));
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
                ti.textureType = normal ? TextureImporterType.NormalMap : TextureImporterType.Default;
                ti.sRGBTexture = color;                       // data maps (mask, roughness, AO, height, normal) are linear
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

            var baseColor = Tex(dir, "T_Calf_BaseColor");
            var normal = Tex(dir, "T_Calf_Normal");
            var urpMS = Tex(dir, "T_Calf_MetallicSmoothness");
            var hdrpMask = Tex(dir, "T_Calf_MaskMap");
            var ao = Tex(dir, "T_Calf_AO");
            var eye = Tex(dir, "T_CalfEye_BaseColor");
            var eyeN = Tex(dir, "T_CalfEye_Normal");

            result["M_Calf_Body"] = MakeLit(mdir + "/M_Calf_Body.mat", pipe, baseColor, normal, urpMS, hdrpMask, ao, 1.0f);
            result["M_Calf_Eye"] = MakeLit(mdir + "/M_Calf_Eye.mat", pipe, eye, eyeN, null, null, null, 0.92f);
            AssetDatabase.SaveAssets();
            return result;
        }

        static Material MakeLit(string path, string pipe, Texture2D albedo, Texture2D normal, Texture2D metallicSmooth,
                                Texture2D mask, Texture2D occlusion, float smoothness)
        {
            string shaderName = pipe == "URP" ? "Universal Render Pipeline/Lit" : pipe == "HDRP" ? "HDRP/Lit" : "Standard";
            var shader = Shader.Find(shaderName);
            if (shader == null) { Debug.LogError($"[Calf] shader {shaderName} not found"); shader = Shader.Find("Standard"); }
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
        static void ConfigureModel(string fbx, Dictionary<string, Material> mats)
        {
            var mi = (ModelImporter)AssetImporter.GetAtPath(fbx);
            mi.globalScale = 1f;
            mi.useFileScale = true;
            mi.importBlendShapes = false;
            mi.importCameras = false;
            mi.importLights = false;
            mi.importNormals = ModelImporterNormals.Import;
            mi.importTangents = ModelImporterTangents.CalculateMikk;
            mi.animationType = ModelImporterAnimationType.Generic;
            mi.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            mi.importAnimation = true;
            mi.animationCompression = ModelImporterAnimationCompression.Optimal;
            mi.materialImportMode = ModelImporterMaterialImportMode.ImportViaMaterialDescription;
            foreach (var kv in mats)
                mi.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), kv.Key), kv.Value);
            mi.SaveAndReimport();

            // motion node = the "Root" bone (path relative to the model root)
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(fbx);
            var rootBone = model.GetComponentsInChildren<Transform>(true).FirstOrDefault(t => t.name == "Root");
            if (rootBone != null) mi.motionNodeName = AnimationUtility.CalculateTransformPath(rootBone, model.transform);
            else Debug.LogWarning("[Calf] bone 'Root' not found; root motion node not set");

            var clips = new List<ModelImporterClipAnimation>();
            foreach (var c in mi.defaultClipAnimations)
            {
                string name = CleanClipName(c.takeName);
                c.name = name;
                ClipSpec.TryGetValue(name, out var spec);
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

        static AnimationClip Clip(string fbx, string name)
        {
            return AssetDatabase.LoadAllAssetsAtPath(fbx).OfType<AnimationClip>()
                .FirstOrDefault(c => !c.name.StartsWith("__preview__") && c.name == name);
        }

        // ------------------------------------------------------------------ animator controller
        static AnimatorController CreateController(string dir, string fbx)
        {
            string path = dir + "/Calf.controller";
            AssetDatabase.DeleteAsset(path);
            var ctrl = AnimatorController.CreateAnimatorControllerAtPath(path);
            ctrl.AddParameter("Speed", AnimatorControllerParameterType.Float);
            foreach (var b in new[] { "Graze", "Lie" }) ctrl.AddParameter(b, AnimatorControllerParameterType.Bool);
            foreach (var t in new[] { "Eat", "Call", "HeadShake", "Leap", "TurnLeft", "TurnRight", "LookAround", "Die" })
                ctrl.AddParameter(t, AnimatorControllerParameterType.Trigger);

            var sm = ctrl.layers[0].stateMachine;
            var loco = ctrl.CreateBlendTreeInController("Locomotion", out BlendTree tree, 0);
            tree.blendType = BlendTreeType.Simple1D;
            tree.blendParameter = "Speed";
            tree.useAutomaticThresholds = false;
            foreach (var (clip, speed) in Locomotion)
            {
                var c = Clip(fbx, clip);
                if (c) tree.AddChild(c, speed); else Debug.LogWarning($"[Calf] clip {clip} missing for locomotion");
            }
            sm.defaultState = loco;

            AnimatorState State(string clip, Vector3 pos)
            {
                var c = Clip(fbx, clip);
                if (!c) { Debug.LogWarning($"[Calf] clip {clip} missing"); return null; }
                var s = sm.AddState(clip, pos); s.motion = c; return s;
            }
            AnimatorStateTransition Go(AnimatorState a, AnimatorState b, float dur, bool exit, float exitTime = 1f)
            {
                if (a == null || b == null) return null;
                var t = a.AddTransition(b); t.duration = dur; t.hasExitTime = exit; if (exit) t.exitTime = exitTime; return t;
            }

            // grazing: Start -> Loop (while Graze) -> End -> Locomotion
            var gS = State("Graze_Start", new Vector3(300, 0)); var gL = State("Graze_Loop", new Vector3(550, 0)); var gE = State("Graze_End", new Vector3(800, 0));
            Go(loco, gS, 0.2f, false)?.AddCondition(AnimatorConditionMode.If, 0, "Graze");
            Go(gS, gL, 0.05f, true, 0.98f);
            Go(gL, gE, 0.1f, false)?.AddCondition(AnimatorConditionMode.IfNot, 0, "Graze");
            Go(gE, loco, 0.2f, true, 0.95f);

            // lying: LieDown -> Lying_Idle (while Lie) -> GetUp -> Locomotion
            var lD = State("LieDown", new Vector3(300, 120)); var lI = State("Lying_Idle", new Vector3(550, 120)); var lU = State("GetUp", new Vector3(800, 120));
            Go(loco, lD, 0.2f, false)?.AddCondition(AnimatorConditionMode.If, 0, "Lie");
            Go(lD, lI, 0.05f, true, 0.98f);
            Go(lI, lU, 0.1f, false)?.AddCondition(AnimatorConditionMode.IfNot, 0, "Lie");
            Go(lU, loco, 0.2f, true, 0.95f);

            // one-shots from locomotion, back when finished
            float y = 240;
            foreach (var (clip, trig) in new[] { ("Eating", "Eat"), ("Call", "Call"), ("HeadShake", "HeadShake"), ("Leap", "Leap"),
                                                ("TurnLeft90", "TurnLeft"), ("TurnRight90", "TurnRight"), ("Idle_LookAround", "LookAround") })
            {
                var s = State(clip, new Vector3(300, y)); y += 60;
                Go(loco, s, 0.2f, false)?.AddCondition(AnimatorConditionMode.If, 0, trig);
                Go(s, loco, 0.2f, true, 0.95f);
            }

            // death from anywhere, no exit
            var death = State("Death", new Vector3(550, 240));
            if (death != null)
            {
                var t = sm.AddAnyStateTransition(death);
                t.AddCondition(AnimatorConditionMode.If, 0, "Die"); t.duration = 0.15f; t.canTransitionToSelf = false;
            }
            AssetDatabase.SaveAssets();
            return ctrl;
        }

        // ------------------------------------------------------------------ prefab
        static GameObject CreatePrefab(string dir, string fbx, AnimatorController ctrl)
        {
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(fbx);
            var inst = (GameObject)PrefabUtility.InstantiatePrefab(model);
            inst.name = "Calf";
            var animator = inst.GetComponent<Animator>() ?? inst.AddComponent<Animator>();
            animator.runtimeAnimatorController = ctrl;
            animator.applyRootMotion = true;
            animator.cullingMode = AnimatorCullingMode.CullUpdateTransforms;

            if (inst.GetComponent<LODGroup>() == null)
            {
                var rs = inst.GetComponentsInChildren<SkinnedMeshRenderer>(true);
                Renderer[] Lod(int i) => rs.Where(r => r.name.EndsWith("_LOD" + i)).Cast<Renderer>().ToArray();
                var lg = inst.AddComponent<LODGroup>();
                lg.SetLODs(new[] { new LOD(0.35f, Lod(0)), new LOD(0.12f, Lod(1)), new LOD(0.02f, Lod(2)) });
                lg.RecalculateBounds();
            }
            foreach (var smr in inst.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                smr.updateWhenOffscreen = false;

            string path = dir + "/Calf.prefab";
            var prefab = PrefabUtility.SaveAsPrefabAsset(inst, path);
            UnityEngine.Object.DestroyImmediate(inst);
            return prefab;
        }
    }
}
#endif
