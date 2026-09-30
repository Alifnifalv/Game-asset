// Common raven asset setup for Unity (Editor only). Adapted from Unity/Rottweiler/Editor/RottweilerSetup.cs (same importer,
// texture, material and prefab code), with the raven's clip table, a third (cutout feather) material and a ground + air
// Animator.
// Menu: Tools > Raven > Setup Raven Asset
//
// Put the whole Unity/Raven folder anywhere under Assets/. The script finds Raven.fbx next to it and:
//   1. configures the model importer: Generic rig, Rig tab > Root node = the "Root" bone (the Avatar's root-motion bone),
//      imported tangents, bones kept, per-clip loop and Root Transform bake settings (TakeOff / Land move the root
//      vertically: their height is NOT baked into the pose)
//   2. configures texture importers (normal map type, linear data maps, 4K; the feather BaseColor keeps its alpha
//      coverage in the mips for the 0.5 cutout)
//   3. creates materials for the active render pipeline (URP Lit / HDRP Lit / Built-in Standard): M_Raven_Body (opaque),
//      M_Raven_Feather (alpha clipping at 0.5 from the BaseColor alpha, back faces culled: the feather strips are closed),
//      M_Raven_Eye (glossy), and remaps the FBX materials
//   4. creates Raven.controller, or rebuilds it in place (see CreateController)
//   5. saves Raven.prefab (a variant of the model) with the Animator (root motion on) and the LODGroup thresholds
// Running it again is safe: materials, controller and prefab keep their asset GUIDs (hand edits are replaced).
//
// NOTE: written without access to a Unity editor or a C# compiler in the build environment (as RottweilerSetup.cs:
// OI-01 / OI-54). Needs a compile and an import check in Unity 2021.3+ / 6.
#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using UnityEngine.Rendering;

namespace RavenAsset.EditorTools
{
    public static class RavenSetup
    {
        const string RootBone = "Root";
        const string Tag = "[Raven]";

        // ------------------------------------------------------------------ clip names
        // Every clip the Animator uses, in one place: if the clip packages rename a clip (e.g. the root-motion / in-place
        // twins "Walk" / "Walk_IP"), change it here (and its row in ClipSpec). The Animator uses the ROOT-MOTION clips;
        // the in-place twins are imported (for game code that moves the object itself) but not placed in the controller.
        static class C
        {
            public const string Idle = "Idle", IdleLook = "Idle_Look", Caw = "Caw", Eat = "Eat", Drink = "Drink";
            public const string Walk = "Walk", WalkIP = "Walk_IP", Hop = "Hop", HopIP = "Hop_IP";
            public const string TurnL = "Turn_L90", TurnR = "Turn_R90";
            public const string Attack = "Attack", HitL = "Hit_L", HitR = "Hit_R", DeathL = "Death_L", DeathR = "Death_R";
            public const string TakeOff = "TakeOff", Fly = "Fly", FlyIP = "Fly_IP", Glide = "Glide", GlideIP = "Glide_IP";
            public const string BankL = "Glide_Bank_L", BankR = "Glide_Bank_R", Land = "Land";
        }

        // clip name -> (loop, root motion kind). Raven_export_manifest.json (next to the FBX) wins for the loop flag and
        // fills in takes this table does not know; a mismatch is logged.
        //   Translate      the root moves on the ground plane / level flight (XZ applied, height and yaw baked)
        //   Turn           the root yaws in place (Turn_L90 / Turn_R90)
        //   TranslateTurn  XZ + yaw (the banked glides: a coordinated turn at 37 deg/s)
        //   Climb          XZ + height: TakeOff climbs 1.3 m, Land descends 1.2 m (the root's height is applied to the
        //                  GameObject; the game keeps gravity off while the raven flies)
        enum RootMotion { None, Translate, Turn, TranslateTurn, Climb }
        static readonly Dictionary<string, (bool loop, RootMotion rm)> ClipSpec = new Dictionary<string, (bool, RootMotion)>
        {
            { C.Idle, (true, RootMotion.None) }, { C.IdleLook, (true, RootMotion.None) }, { C.Caw, (false, RootMotion.None) },
            { C.Eat, (true, RootMotion.None) }, { C.Drink, (true, RootMotion.None) },
            { C.Walk, (true, RootMotion.Translate) }, { C.WalkIP, (true, RootMotion.None) },
            { C.Hop, (true, RootMotion.Translate) }, { C.HopIP, (true, RootMotion.None) },
            { C.TurnL, (false, RootMotion.Turn) }, { C.TurnR, (false, RootMotion.Turn) },
            { C.Attack, (false, RootMotion.Translate) }, { C.HitL, (false, RootMotion.None) }, { C.HitR, (false, RootMotion.None) },
            { C.DeathL, (false, RootMotion.None) }, { C.DeathR, (false, RootMotion.None) },   // spec: "small RM"; the export has none
            { C.TakeOff, (false, RootMotion.Climb) }, { C.Land, (false, RootMotion.Climb) },
            { C.Fly, (true, RootMotion.Translate) }, { C.FlyIP, (true, RootMotion.None) },
            { C.Glide, (true, RootMotion.Translate) }, { C.GlideIP, (true, RootMotion.None) },
            { C.BankL, (true, RootMotion.TranslateTurn) }, { C.BankR, (true, RootMotion.TranslateTurn) },
        };

        // Ground gaits (m/s, export values; checked against the root speed Unity measures on the imported clip, a
        // difference of more than 10% is logged). Walk (alternating, 30 f) and Hop (two-footed, 20 f) are separate states,
        // NOT blended: a normalised-time blend of an alternating and a synchronous gait half-alternates the feet and skates.
        // The game drives Speed (m/s) and may time-scale the gaits with WalkRate / HopRate (default 1; e.g.
        // WalkRate = Speed / 0.16 clamped to 0.7-1.4) so the planted feet match the object's motion.
        const float WalkSpeed = 0.16f, HopSpeed = 0.45f;
        const float SpeedStart = 0.04f, SpeedStop = 0.02f;   // Idle -> Walk above 0.04 m/s, back to Idle below 0.02 m/s
        const float HopStart = 0.30f, HopStop = 0.26f;       // Walk -> Hop above 0.30 m/s, Hop -> Walk below 0.26 m/s
        // switch points (normalised time): the Walk's double supports are f8-15 and f23-30 (of 30; swings L f0-8, R f15-23),
        // so a 0.2 s (6 f) transition started at f8.5 / f23.5 ends before the next swing; the Hop is on the ground f16-20
        // and f0-8 (of 20)
        const float WalkSwitchA = 0.28f, WalkSwitchB = 0.78f, HopSwitch = 0.95f;
        const float FlightSpeed = 8f;                         // Fly / Glide / Glide_Bank root speed (m/s)
        const float TurnStart = 0.5f;                         // |Turn| above this starts a 90 deg ground turn from Idle

        // ground one-shots: triggered from Idle / Walk / Hop / Idle_Look, then back to Walk (Speed) or Idle
        static readonly (string clip, string trigger)[] OneShots =
        {
            (C.Caw, "Caw"), (C.Eat, "Eat"), (C.Drink, "Drink"), (C.Attack, "Attack")
        };
        const string ReadyTag = "Ready", AirTag = "Air", DeadTag = "Dead";   // state tags for game code

        // Standard (Specular setup) / URP Specular workflow with T_Raven_*_SpecularSmoothness (spec 5.2: the tinted F0
        // carries the violet / blue-violet sheen). Off by default: the BaseColor already holds the metallic-workflow
        // tints (tools/raven/raven_textures.py), which every pipeline renders the same way. HDRP always uses the MaskMap.
        static readonly bool UseSpecularSetup = false;

        [MenuItem("Tools/Raven/Setup Raven Asset")]
        public static void Setup()
        {
            string fbx = FindFbx();
            if (fbx == null) { EditorUtility.DisplayDialog("Raven setup", "Raven.fbx not found under Assets/.", "OK"); return; }
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
            Debug.Log($"{Tag} setup complete: {AssetDatabase.GetAssetPath(prefab)} (pipeline: {PipelineName()})");
        }

        // ------------------------------------------------------------------ discovery
        static string FindFbx()
        {
            return AssetDatabase.FindAssets("Raven t:Model")
                .Select(AssetDatabase.GUIDToAssetPath)
                .FirstOrDefault(p => Path.GetFileName(p).Equals("Raven.fbx", StringComparison.OrdinalIgnoreCase));
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
                bool cutout = n == "T_Raven_Feather_BaseColor";      // RGBA: A = feather cutout (threshold 0.5)
                // Default type for every data map, AO included: URP / Built-in Lit read occlusion from G, which a
                // single-channel (R8 / BC4) import would leave at 0
                ti.textureType = normal ? TextureImporterType.NormalMap : TextureImporterType.Default;
                ti.sRGBTexture = color;                       // data maps (mask, roughness, AO, specular F0, normal) are linear
                ti.maxTextureSize = 4096;
                ti.mipmapEnabled = true;
                ti.alphaIsTransparency = false;               // no colour bleed into the cut-out texels: the atlas is painted there
                ti.alphaSource = TextureImporterAlphaSource.FromInput;
                // keep the cutout coverage in the mips, so the frayed feather edges do not erode at a distance
                ti.mipMapsPreserveCoverage = cutout;
                if (cutout) ti.alphaTestReferenceValue = 0.5f;
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
        class TexSet
        {
            public Texture2D albedo, normal, metallicSmooth, specSmooth, mask, occlusion;
            public static TexSet Load(string dir, string prefix) => new TexSet
            {
                albedo = Tex(dir, prefix + "_BaseColor"), normal = Tex(dir, prefix + "_Normal"),
                metallicSmooth = Tex(dir, prefix + "_MetallicSmoothness"), specSmooth = Tex(dir, prefix + "_SpecularSmoothness"),
                mask = Tex(dir, prefix + "_MaskMap"), occlusion = Tex(dir, prefix + "_AO"),
            };
        }

        static Dictionary<string, Material> CreateMaterials(string dir)
        {
            string mdir = dir + "/Materials";
            if (!AssetDatabase.IsValidFolder(mdir)) AssetDatabase.CreateFolder(dir, "Materials");
            string pipe = PipelineName();
            var result = new Dictionary<string, Material>();
            var eye = new TexSet { albedo = Tex(dir, "T_RavenEye_BaseColor") };
            result["M_Raven_Body"] = MakeLit(mdir + "/M_Raven_Body.mat", pipe, TexSet.Load(dir, "T_Raven"), 0.45f, false);
            result["M_Raven_Feather"] = MakeLit(mdir + "/M_Raven_Feather.mat", pipe, TexSet.Load(dir, "T_Raven_Feather"), 0.65f, true);
            result["M_Raven_Eye"] = MakeLit(mdir + "/M_Raven_Eye.mat", pipe, eye, 0.92f, false);
            AssetDatabase.SaveAssets();
            return result;
        }

        // smoothness: used only when the set has no smoothness map (the eye)
        static Material MakeLit(string path, string pipe, TexSet t, float smoothness, bool cutout)
        {
            bool spec = UseSpecularSetup && t.specSmooth != null && pipe != "HDRP";
            string shaderName = pipe == "URP" ? "Universal Render Pipeline/Lit" : pipe == "HDRP" ? "HDRP/Lit"
                              : spec ? "Standard (Specular setup)" : "Standard";
            var shader = Shader.Find(shaderName);
            if (shader == null) { Debug.LogError($"{Tag} shader {shaderName} not found"); shader = Shader.Find("Standard"); }
            var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null) { mat = new Material(shader); AssetDatabase.CreateAsset(mat, path); }
            else mat.shader = shader;
            mat.shaderKeywords = new string[0];            // a re-run may switch workflow / cutout: start clean

            if (pipe == "URP")
            {
                if (t.albedo) mat.SetTexture("_BaseMap", t.albedo);
                mat.SetColor("_BaseColor", Color.white);
                if (t.normal) { mat.SetTexture("_BumpMap", t.normal); mat.SetFloat("_BumpScale", 1f); mat.EnableKeyword("_NORMALMAP"); }
                mat.SetFloat("_Metallic", 0f);
                var gloss = spec ? t.specSmooth : t.metallicSmooth;
                if (spec)
                {
                    mat.SetFloat("_WorkflowMode", 0f); mat.EnableKeyword("_SPECULAR_SETUP");
                    mat.SetTexture("_SpecGlossMap", t.specSmooth); mat.SetColor("_SpecColor", Color.white);
                }
                else { mat.SetFloat("_WorkflowMode", 1f); if (gloss) mat.SetTexture("_MetallicGlossMap", gloss); }
                if (gloss)
                {
                    mat.EnableKeyword("_METALLICSPECGLOSSMAP");
                    mat.SetFloat("_SmoothnessTextureChannel", 0f);   // smoothness from the metallic / specular map alpha
                    mat.SetFloat("_Smoothness", 1f);
                }
                else mat.SetFloat("_Smoothness", smoothness);
                if (t.occlusion) { mat.SetTexture("_OcclusionMap", t.occlusion); mat.SetFloat("_OcclusionStrength", 1f); mat.EnableKeyword("_OCCLUSIONMAP"); }
                mat.SetFloat("_Surface", 0f);                        // opaque; the feathers are alpha-tested, not blended
                mat.SetFloat("_Cull", (float)CullMode.Back);
                mat.SetFloat("_AlphaClip", cutout ? 1f : 0f);
                mat.SetFloat("_Cutoff", 0.5f);
                if (cutout) mat.EnableKeyword("_ALPHATEST_ON");
            }
            else if (pipe == "HDRP")
            {
                if (t.albedo) mat.SetTexture("_BaseColorMap", t.albedo);
                mat.SetColor("_BaseColor", Color.white);
                if (t.normal) { mat.SetTexture("_NormalMap", t.normal); mat.SetFloat("_NormalScale", 1f); mat.EnableKeyword("_NORMALMAP"); mat.EnableKeyword("_NORMALMAP_TANGENT_SPACE"); }
                if (t.mask)
                {
                    mat.SetTexture("_MaskMap", t.mask); mat.EnableKeyword("_MASKMAP");
                    mat.SetFloat("_SmoothnessRemapMin", 0f); mat.SetFloat("_SmoothnessRemapMax", 1f);
                    mat.SetFloat("_AORemapMin", 0f); mat.SetFloat("_AORemapMax", 1f);
                    mat.SetFloat("_MetallicRemapMin", 0f); mat.SetFloat("_MetallicRemapMax", 0f);
                }
                else { mat.SetFloat("_Smoothness", smoothness); mat.SetFloat("_Metallic", 0f); }
                mat.SetFloat("_AlphaCutoffEnable", cutout ? 1f : 0f);
                mat.SetFloat("_AlphaCutoff", 0.5f);
                mat.SetFloat("_DoubleSidedEnable", 0f);
                if (cutout) mat.EnableKeyword("_ALPHATEST_ON");
                // let HDRP rebuild keywords/passes if its editor assembly is present (reflection: no hard HDRP dependency)
                var ht = Type.GetType("UnityEditor.Rendering.HighDefinition.HDShaderUtils, Unity.RenderPipelines.HighDefinition.Editor");
                var m = ht?.GetMethod("ResetMaterialKeywords", new[] { typeof(Material) });
                m?.Invoke(null, new object[] { mat });
            }
            else
            {
                if (t.albedo) mat.SetTexture("_MainTex", t.albedo);
                mat.SetColor("_Color", Color.white);
                if (t.normal) { mat.SetTexture("_BumpMap", t.normal); mat.EnableKeyword("_NORMALMAP"); }
                if (spec)
                {
                    mat.SetTexture("_SpecGlossMap", t.specSmooth); mat.EnableKeyword("_SPECGLOSSMAP");
                    mat.SetFloat("_GlossMapScale", 1f);
                }
                else
                {
                    mat.SetFloat("_Metallic", 0f);
                    if (t.metallicSmooth)
                    {
                        mat.SetTexture("_MetallicGlossMap", t.metallicSmooth); mat.EnableKeyword("_METALLICGLOSSMAP");
                        mat.SetFloat("_GlossMapScale", 1f);
                    }
                    else mat.SetFloat("_Glossiness", smoothness);
                }
                mat.SetFloat("_SmoothnessTextureChannel", 0f);    // from the metallic / specular map alpha (the albedo alpha is the cutout)
                if (t.occlusion) mat.SetTexture("_OcclusionMap", t.occlusion);
                // Standard shader render mode (what StandardShaderGUI.SetupMaterialWithBlendMode does): 0 Opaque, 1 Cutout
                mat.SetFloat("_Mode", cutout ? 1f : 0f);
                mat.SetFloat("_Cutoff", 0.5f);
                mat.SetInt("_SrcBlend", (int)BlendMode.One);
                mat.SetInt("_DstBlend", (int)BlendMode.Zero);
                mat.SetInt("_ZWrite", 1);
                mat.SetOverrideTag("RenderType", cutout ? "TransparentCutout" : "");
                if (cutout) mat.EnableKeyword("_ALPHATEST_ON");
            }
            mat.renderQueue = cutout ? (int)RenderQueue.AlphaTest : -1;   // -1: the shader's default queue (Geometry)
            EditorUtility.SetDirty(mat);
            return mat;
        }

        // ------------------------------------------------------------------ model importer
        [Serializable] class ManifestTake { public string name = ""; public bool cyclic = false; public bool root_motion = false; }
        [Serializable] class Manifest { public ManifestTake[] takes = new ManifestTake[0]; }

        static Dictionary<string, ManifestTake> LoadManifest(string dir)
        {
            var result = new Dictionary<string, ManifestTake>();
            var json = AssetDatabase.LoadAssetAtPath<TextAsset>(dir + "/Raven_export_manifest.json");
            if (json == null) return result;
            try
            {
                var m = JsonUtility.FromJson<Manifest>(json.text);
                if (m?.takes != null)
                    foreach (var t in m.takes) if (!string.IsNullOrEmpty(t.name)) result[t.name] = t;
            }
            catch (ArgumentException e) { Debug.LogWarning($"{Tag} could not read Raven_export_manifest.json ({e.Message}); using the clip table"); }
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
            mi.optimizeBones = false;                              // "Strip Bones" off: Root (root motion) and Lid.L/R carry no weights
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
                Debug.LogWarning($"{Tag} bone '{RootBone}' not found; set Rig > Root node by hand");

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
                        Debug.LogWarning($"{Tag} {name}: manifest says loop={take.cyclic} root_motion={take.root_motion}; using the manifest");
                    spec.loop = take.cyclic;
                    if (!take.root_motion) spec.rm = RootMotion.None;
                    else if (!known || spec.rm == RootMotion.None) spec.rm = RootMotion.TranslateTurn;
                }
                else if (!known) Debug.LogWarning($"{Tag} take {name}: not in the clip table or the manifest; imported as an in-place one-shot");
                c.loopTime = spec.loop;
                c.loopPose = false;                 // clips are authored with an exact seam (first frame == last frame)
                bool translates = spec.rm == RootMotion.Translate || spec.rm == RootMotion.TranslateTurn || spec.rm == RootMotion.Climb;
                bool turns = spec.rm == RootMotion.Turn || spec.rm == RootMotion.TranslateTurn;
                c.lockRootRotation = !turns;        // "Bake Into Pose" when the clip does not turn the root
                c.keepOriginalOrientation = true;
                c.lockRootHeightY = spec.rm != RootMotion.Climb;   // only TakeOff / Land move the root vertically
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
            if (p == null) { Debug.LogWarning($"{Tag} could not set Rig > Root node; set it to '{bone}' by hand"); return; }
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
            if (v < 0.02f)
            {
                Debug.LogWarning($"{Tag} {c.name}: no root motion in Unity ({v:F3} m/s); check Rig > Root node = {RootBone}. Threshold {expected} m/s");
                return expected;
            }
            if (Mathf.Abs(v - expected) > 0.1f * expected)
                Debug.LogWarning($"{Tag} {c.name}: root speed {v:F3} m/s in Unity, {expected} m/s in the export");
            else Debug.Log($"{Tag} {c.name}: root speed {v:F3} m/s (export {expected} m/s)");
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

        // One layer ("Base Layer"), two groups of states (flat, so every transition is a plain state-to-state one):
        //   GROUND (tag Ready): Idle (default) <-> Walk (Speed > 0.04 m/s; back below 0.02 at a double support) <-> Hop
        //     (Speed > 0.30 m/s at the Walk's double support; back to Walk below 0.26 at the Hop's ground phase): two
        //     states, not a blend (see WalkSpeed); Idle_Look while the LookAround bool is set; Turn_L90 / Turn_R90 from
        //     Idle while Turn < -0.5 / > 0.5 (repeats while held); one-shots Caw / Eat / Drink / Attack (triggers); Hit
        //     (trigger, side from the Left bool: Hit_L / Hit_R); Die (trigger + Left: Death_L / Death_R, tag Dead, final).
        //   AIR (tag Air): IsFlying = true starts TakeOff (from Idle / Walk / Hop / Idle_Look), which ends on the Fly pose
        //     and phase -> Fly (the wingbeat, Flap >= 0.5; Flap defaults to 1) <-> Glide (Flap < 0.5; a 1D blend tree on
        //     Turn: -1 Glide_Bank_L, 0 Glide, +1 Glide_Bank_R). Fly and Glide are separate states switched at the end of a
        //     wingbeat (both start on the neutral flight pose, Fly f0), not a Flap blend (a normalised-time blend of the
        //     20 f wingbeat with the 120 f glide slows the beat down 3x). IsFlying = false plays Land from Glide at once,
        //     from Fly at the end of a wingbeat; Land ends on the standing pose -> Idle / Walk. There is no death / hit in
        //     the air (no Death_Fly clip).
        static AnimatorController CreateController(string dir, string fbx)
        {
            string path = dir + "/Raven.controller";
            var ctrl = LoadOrResetController(path);
            foreach (var f in new[] { "Speed", "Turn" })
                ctrl.AddParameter(f, AnimatorControllerParameterType.Float);
            foreach (var f in new[] { "Flap", "WalkRate", "HopRate" })     // default 1: flapping flight, gaits at export speed
                ctrl.AddParameter(new AnimatorControllerParameter { name = f, type = AnimatorControllerParameterType.Float, defaultFloat = 1f });
            foreach (var b in new[] { "IsFlying", "LookAround", "Left" })
                ctrl.AddParameter(b, AnimatorControllerParameterType.Bool);
            foreach (var t in OneShots.Select(o => o.trigger).Concat(new[] { "Hit", "Die" }))
                ctrl.AddParameter(t, AnimatorControllerParameterType.Trigger);
            var sm = ctrl.layers[0].stateMachine;

            AnimatorState State(string clip, float x, float y, string tag = "")
            {
                var c = Clip(fbx, clip);
                if (!c) { Debug.LogWarning($"{Tag} clip {clip} missing"); return null; }
                var s = sm.AddState(clip, new Vector3(x, y)); s.motion = c; s.tag = tag; return s;
            }
            AnimatorStateTransition Go(AnimatorState a, AnimatorState b, float dur, bool exit, float exitTime = 1f)
            {
                if (a == null || b == null) return null;
                var t = a.AddTransition(b); t.duration = dur; t.hasExitTime = exit; if (exit) t.exitTime = exitTime; return t;
            }
            BlendTree Tree(string name, string param)
            {
                var tree = new BlendTree { name = name, blendType = BlendTreeType.Simple1D, blendParameter = param, useAutomaticThresholds = false };
                AssetDatabase.AddObjectToAsset(tree, ctrl);
                return tree;
            }
            void Child(BlendTree tree, string clip, float threshold)
            {
                var c = Clip(fbx, clip);
                if (c) tree.AddChild(c, threshold); else Debug.LogWarning($"{Tag} clip {clip} missing for blend tree {tree.name}");
            }

            // ---------------- ground
            var idle = State(C.Idle, 250, 0, ReadyTag);
            if (idle == null) { idle = sm.AddState(C.Idle, new Vector3(250, 0)); idle.tag = ReadyTag; }
            sm.defaultState = idle;

            // Walk and Hop: separate states (never blended), time-scaled by WalkRate / HopRate
            var loco = State(C.Walk, 250, 160, ReadyTag);
            var hop = State(C.Hop, 500, 160, ReadyTag);
            foreach (var (st, rate, speed) in new[] { (loco, "WalkRate", WalkSpeed), (hop, "HopRate", HopSpeed) })
            {
                if (st == null) continue;
                st.speedParameterActive = true; st.speedParameter = rate;
                RootSpeed((AnimationClip)st.motion, speed);          // a check only
            }
            Go(idle, loco, 0.2f, false)?.AddCondition(AnimatorConditionMode.Greater, SpeedStart, "Speed");
            foreach (var et in new[] { WalkSwitchA, WalkSwitchB })  // stop / change gait at a double support
            {
                Go(loco, idle, 0.2f, true, et)?.AddCondition(AnimatorConditionMode.Less, SpeedStop, "Speed");
                Go(loco, hop, 0.1f, true, et)?.AddCondition(AnimatorConditionMode.Greater, HopStart, "Speed");
            }
            Go(hop, loco, 0.1f, true, HopSwitch)?.AddCondition(AnimatorConditionMode.Less, HopStop, "Speed");
            Go(hop, idle, 0.2f, true, HopSwitch)?.AddCondition(AnimatorConditionMode.Less, SpeedStop, "Speed");

            var look = State(C.IdleLook, 0, 0, ReadyTag);
            Go(idle, look, 0.3f, false)?.AddCondition(AnimatorConditionMode.If, 0, "LookAround");
            Go(look, idle, 0.3f, false)?.AddCondition(AnimatorConditionMode.IfNot, 0, "LookAround");
            Go(look, loco, 0.2f, false)?.AddCondition(AnimatorConditionMode.Greater, SpeedStart, "Speed");

            var ready = new List<AnimatorState> { idle, loco, hop, look }.Where(s => s != null).ToList();
            void Enter(AnimatorState s, float dur, AnimatorConditionMode mode, string param, float threshold = 0f,
                       (AnimatorConditionMode mode, string param)? extra = null, IEnumerable<AnimatorState> from = null)
            {
                foreach (var r in from ?? ready)
                {
                    var t = Go(r, s, dur, false);
                    if (t == null) continue;
                    t.AddCondition(mode, threshold, param);
                    if (extra.HasValue) t.AddCondition(extra.Value.mode, 0, extra.Value.param);
                }
            }
            void Leave(AnimatorState s, float dur, float exitTime)
            {
                Go(s, loco, dur, true, exitTime)?.AddCondition(AnimatorConditionMode.Greater, SpeedStart, "Speed");
                Go(s, idle, dur, true, exitTime);
            }
            var standing = new List<AnimatorState>(ready);          // states Hit / Die may start from

            // 90 deg turns on the spot (root yaw), from Idle only (the walk steers with the object's own rotation)
            var turnL = State(C.TurnL, 0, 240, ReadyTag);
            var turnR = State(C.TurnR, 500, 240, ReadyTag);
            Enter(turnL, 0.15f, AnimatorConditionMode.Less, "Turn", -TurnStart, from: new[] { idle });
            Enter(turnR, 0.15f, AnimatorConditionMode.Greater, "Turn", TurnStart, from: new[] { idle });
            Leave(turnL, 0.15f, 0.95f); Leave(turnR, 0.15f, 0.95f);
            standing.AddRange(new[] { turnL, turnR });

            // one-shots (Eat / Drink are loops in the FBX: the trigger plays one full bout)
            float y = -120;
            foreach (var (clip, trig) in OneShots)
            {
                var s = State(clip, 550, y += 60);
                Enter(s, 0.2f, AnimatorConditionMode.If, trig);
                Leave(s, 0.2f, 0.95f);
                standing.Add(s);
            }

            // hits: side from the Left bool (Hit_L = hit on the left side, flinches to the right)
            var hitL = State(C.HitL, 800, -60); var hitR = State(C.HitR, 800, 0);
            var hitFrom = standing.Where(s => s != null).ToList();
            Enter(hitL, 0.1f, AnimatorConditionMode.If, "Hit", 0f, (AnimatorConditionMode.If, "Left"), hitFrom);
            Enter(hitR, 0.1f, AnimatorConditionMode.If, "Hit", 0f, (AnimatorConditionMode.IfNot, "Left"), hitFrom);
            Leave(hitL, 0.15f, 0.9f); Leave(hitR, 0.15f, 0.9f);
            standing.AddRange(new[] { hitL, hitR });

            // ---------------- air
            var takeOff = State(C.TakeOff, 250, 420, AirTag);
            var fly = State(C.Fly, 250, 560, AirTag);                 // the cruise wingbeat (Flap >= 0.5)
            var glideTree = Tree("Glide", "Turn");                    // Flap < 0.5: the glide, banked by Turn
            Child(glideTree, C.BankL, -1f); Child(glideTree, C.Glide, 0f); Child(glideTree, C.BankR, 1f);
            var glide = sm.AddState("Glide", new Vector3(500, 560));
            glide.motion = glideTree; glide.tag = AirTag;
            foreach (var c in new[] { C.Fly, C.Glide, C.BankL, C.BankR })
            {
                var clip = Clip(fbx, c);
                if (clip) RootSpeed(clip, FlightSpeed);            // a check only: every flight clip moves at 8 m/s
            }
            var land = State(C.Land, 0, 560, AirTag);

            Enter(takeOff, 0.2f, AnimatorConditionMode.If, "IsFlying");
            // TakeOff ends exactly on Fly frame 0 (pose, phase and speed): a short blend into Fly at 0
            var toFly = Go(takeOff, fly, 0.1f, true, 0.97f);
            if (toFly != null) toFly.offset = 0f;
            // Fly -> Glide at the end of a wingbeat (Fly f20 = Glide f0 = the neutral flight pose); Glide -> Fly at once,
            // into the start of a beat (the glide trims stay within a few degrees of that pose)
            var toGlide = Go(fly, glide, 0.15f, true, 0.98f);
            if (toGlide != null) { toGlide.offset = 0f; toGlide.AddCondition(AnimatorConditionMode.Less, 0.5f, "Flap"); }
            var toBeat = Go(glide, fly, 0.2f, false);
            if (toBeat != null) { toBeat.offset = 0f; toBeat.AddCondition(AnimatorConditionMode.Greater, 0.5f, "Flap"); }
            // Land starts on the neutral glide pose: from Glide at once, from Fly at the end of a wingbeat
            // (IsFlying cleared during TakeOff: the climb finishes, Fly plays to the end of its beat, then Land)
            Go(glide, land, 0.25f, false)?.AddCondition(AnimatorConditionMode.IfNot, 0, "IsFlying");
            Go(fly, land, 0.2f, true, 0.98f)?.AddCondition(AnimatorConditionMode.IfNot, 0, "IsFlying");
            Leave(land, 0.2f, 0.95f);

            // death from every ground state (the clips start on the standing pose), checked before the other transitions
            var deathL = State(C.DeathL, 900, 200, DeadTag); var deathR = State(C.DeathR, 900, 280, DeadTag);
            foreach (var s in standing.Where(s => s != null))
            {
                foreach (var (dst, side) in new[] { (deathL, AnimatorConditionMode.If), (deathR, AnimatorConditionMode.IfNot) })
                {
                    var t = Go(s, dst, 0.2f, false);
                    if (t == null) continue;
                    t.AddCondition(AnimatorConditionMode.If, 0, "Die");
                    t.AddCondition(side, 0, "Left");
                }
                s.transitions = s.transitions.OrderBy(t => t.destinationState != null &&
                    (t.destinationState == deathL || t.destinationState == deathR) ? 0 : 1).ToArray();
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
            inst.name = "Raven";
            var animator = inst.GetComponent<Animator>();
            if (animator == null) animator = inst.AddComponent<Animator>();   // Unity null check (no ?? on UnityEngine.Object)
            animator.runtimeAnimatorController = ctrl;
            animator.applyRootMotion = true;
            animator.cullingMode = AnimatorCullingMode.CullUpdateTransforms;

            // The importer usually creates the LODGroup from the _LOD0.._LOD2 names; apply the documented thresholds either
            // way (a 0.6 m bird: lower screen-height thresholds than the calf / dog)
            var rs = inst.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            Renderer[] Lod(int i) => rs.Where(r => r.name.EndsWith("_LOD" + i)).Cast<Renderer>().ToArray();
            var lg = inst.GetComponent<LODGroup>();
            if (lg == null) lg = inst.AddComponent<LODGroup>();
            lg.SetLODs(new[] { new LOD(0.25f, Lod(0)), new LOD(0.08f, Lod(1)), new LOD(0.01f, Lod(2)) });
            lg.RecalculateBounds();
            for (int i = 0; i < 3; i++) if (Lod(i).Length == 0) Debug.LogWarning($"{Tag} no renderer named *_LOD{i}");
            foreach (var smr in rs)
                smr.updateWhenOffscreen = false;

            string path = dir + "/Raven.prefab";
            var prefab = PrefabUtility.SaveAsPrefabAsset(inst, path);
            UnityEngine.Object.DestroyImmediate(inst);
            return prefab;
        }
    }
}
#endif
