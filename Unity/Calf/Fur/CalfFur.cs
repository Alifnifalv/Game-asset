// Optional URP shell fur for the calf's LOD0 body.
// Add to the Calf prefab root (the object with the Animator) and assign a material that uses Calf/URP/ShellFur
// (CalfSetup creates Materials/M_Calf_Fur in URP projects). On Start it appends `shells` shell materials.
// Preferred path: the body is the LAST submesh of Calf_LOD0 (the exporter guarantees this), so the shells are appended
// as extra materials and Unity redraws the body submesh once per shell (no mesh copy, deforms with the rig, LOD0 only).
// Fallback: a fur-only copy of the body submesh on a child renderer (needs Read/Write enabled on the model).
// The shell materials are shared by every CalfFur with the same fur material, shell count and length, so a herd adds
// `shells` materials in total, not `shells` per calf. Disabling the component removes the shells; enabling it (or
// calling Build() after changing the settings or the fur material) puts them back.
// Cost: `shells` extra draws of the ~47k-triangle LOD0 body per calf (plus the same in the depth prepass when URP
// runs one); use on hero / close-up calves only. URP only: in other pipelines it logs a warning and does nothing.
// NOTE: written without a Unity editor in the build environment; verify once in Unity (URP).
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace CalfAsset
{
    [DisallowMultipleComponent]
    public class CalfFur : MonoBehaviour
    {
        [Tooltip("Material using the Calf/URP/ShellFur shader (base map, fur mask, strand noise).")]
        public Material furMaterial;
        [Tooltip("Name of the LOD0 body renderer.")]
        public string lod0Name = "Calf_LOD0";
        [Tooltip("Name of the body material on that renderer (the submesh that gets fur).")]
        public string bodyMaterialName = "M_Calf_Body";
        [Range(4, 24)] public int shells = 12;
        [Range(0.002f, 0.03f)] public float furLength = 0.009f;

        SkinnedMeshRenderer _furOnSource;    // preferred path: shells appended to the LOD0 renderer
        int _baseMaterialCount;
        SkinnedMeshRenderer _fur;            // fallback child renderer
        Mesh _furMesh;
        ShellKey _key;
        bool _hasShells;
        bool _started;

        // ------------------------------------------------------------------ shared shell materials
        struct ShellKey : System.IEquatable<ShellKey>
        {
            public Material material; public int shells; public float length;
            public bool Equals(ShellKey o) { return material == o.material && shells == o.shells && length == o.length; }
            public override bool Equals(object o) { return o is ShellKey k && Equals(k); }
            public override int GetHashCode()
            {
                int h = material ? material.GetHashCode() : 0;      // UnityEngine.Object hashes by instance id
                return (h * 397 ^ shells) * 397 ^ length.GetHashCode();
            }
        }
        sealed class ShellSet { public Material[] materials; public int users; }
        static readonly Dictionary<ShellKey, ShellSet> s_ShellSets = new Dictionary<ShellKey, ShellSet>();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetShared() { s_ShellSets.Clear(); }      // Enter Play Mode without a domain reload

        static Material[] AcquireShells(ShellKey key)
        {
            if (!s_ShellSets.TryGetValue(key, out var set))
            {
                set = new ShellSet { materials = new Material[key.shells] };
                for (int s = 0; s < key.shells; s++)
                    set.materials[s] = new Material(key.material) { name = key.material.name + "_Shell" + (s + 1) };
                s_ShellSets.Add(key, set);
            }
            // refresh from the fur material on every Build(), so edits to it reach the shells
            for (int s = 0; s < key.shells; s++)
            {
                var m = set.materials[s];
                m.CopyPropertiesFromMaterial(key.material);
                m.SetFloat("_ShellIndex", s + 1);
                m.SetFloat("_ShellCount", key.shells);
                m.SetFloat("_FurLength", key.length);
                m.renderQueue = key.material.renderQueue + s;    // draw inner shells first
            }
            set.users++;
            return set.materials;
        }

        static void ReleaseShells(ShellKey key)
        {
            if (!s_ShellSets.TryGetValue(key, out var set) || --set.users > 0) return;
            foreach (var m in set.materials) if (m) Destroy(m);
            s_ShellSets.Remove(key);
        }

        static bool UrpActive()
        {
            var rp = GraphicsSettings.currentRenderPipeline;
            return rp != null && rp.GetType().Name.Contains("Universal");
        }

        // ------------------------------------------------------------------ lifecycle
        void Start() { _started = true; Build(); }
        void OnEnable() { if (_started) Build(); }      // first build waits for Start, so scripts can assign furMaterial after AddComponent
        void OnDisable() { RemoveShells(); }

        public void Build()
        {
            RemoveShells();                                   // rebuilding replaces the previous set
            if (furMaterial == null) { Debug.LogWarning("[CalfFur] no fur material assigned", this); return; }
            if (!UrpActive() || furMaterial.shader == null || !furMaterial.shader.isSupported)
            {
                Debug.LogWarning("[CalfFur] shell fur needs URP and the Calf/URP/ShellFur shader; no fur added", this);
                return;
            }
            SkinnedMeshRenderer src = null;
            foreach (var r in GetComponentsInChildren<SkinnedMeshRenderer>(true))
                if (r.name == lod0Name) { src = r; break; }
            if (src == null) { Debug.LogWarning($"[CalfFur] renderer {lod0Name} not found", this); return; }

            Mesh mesh = src.sharedMesh;
            int sub = -1;
            var mats = src.sharedMaterials;
            for (int i = 0; i < mats.Length && i < mesh.subMeshCount; i++)
                if (mats[i] && mats[i].name.StartsWith(bodyMaterialName)) { sub = i; break; }
            if (sub < 0)
            {
                // no silent fallback: submesh 0 is the eye
                Debug.LogWarning($"[CalfFur] no material named {bodyMaterialName}* on {lod0Name}; no fur added", this);
                return;
            }

            _key = new ShellKey { material = furMaterial, shells = shells, length = furLength };
            var shellMats = AcquireShells(_key);
            _hasShells = true;

            if (sub == mesh.subMeshCount - 1)
            {
                // Preferred path (the exporter puts the body submesh last): a renderer with more materials than submeshes
                // renders the LAST submesh once per extra material -> append the shells; no mesh copy, no extra skinning.
                var all = new List<Material>(mats);
                while (all.Count > mesh.subMeshCount) all.RemoveAt(all.Count - 1);
                all.AddRange(shellMats);
                src.sharedMaterials = all.ToArray();
                _furOnSource = src;
                _baseMaterialCount = mesh.subMeshCount;
                return;                                           // renderer is already in LOD0 of the LODGroup
            }

            // Fallback: body is not the last submesh -> fur-only copy of the body submesh on a child renderer.
            // Needs Read/Write enabled on the model (Model import settings) to read the vertex data.
            if (!mesh.isReadable)
            {
                Debug.LogWarning("[CalfFur] enable Read/Write on the model or export the body as the last submesh", this);
                RemoveShells();
                return;
            }
            _furMesh = new Mesh { name = mesh.name + "_Fur", indexFormat = mesh.indexFormat };
            _furMesh.vertices = mesh.vertices;
            _furMesh.normals = mesh.normals;
            _furMesh.uv = mesh.uv;
            _furMesh.boneWeights = mesh.boneWeights;
            _furMesh.bindposes = mesh.bindposes;
            _furMesh.subMeshCount = 1;
            _furMesh.SetTriangles(mesh.GetTriangles(sub), 0);
            _furMesh.bounds = mesh.bounds;

            var go = new GameObject(lod0Name + "_Fur");
            go.transform.SetParent(src.transform.parent, false);
            go.transform.localPosition = src.transform.localPosition;
            go.transform.localRotation = src.transform.localRotation;
            go.transform.localScale = src.transform.localScale;
            _fur = go.AddComponent<SkinnedMeshRenderer>();
            _fur.sharedMesh = _furMesh;
            _fur.bones = src.bones;
            _fur.rootBone = src.rootBone;
            _fur.localBounds = src.localBounds;
            _fur.shadowCastingMode = ShadowCastingMode.Off;
            _fur.receiveShadows = true;
            _fur.updateWhenOffscreen = false;
            _fur.sharedMaterials = shellMats;

            // fur only at LOD0
            var lg = GetComponent<LODGroup>();
            if (lg)
            {
                var lods = lg.GetLODs();
                if (lods.Length > 0)
                {
                    var rs = new List<Renderer>(lods[0].renderers) { _fur };
                    lods[0].renderers = rs.ToArray();
                    lg.SetLODs(lods);
                }
            }
        }

        void RemoveShells()
        {
            if (_furOnSource)
            {
                var mats = _furOnSource.sharedMaterials;
                if (mats.Length > _baseMaterialCount)
                {
                    var keep = new Material[_baseMaterialCount];
                    System.Array.Copy(mats, keep, _baseMaterialCount);
                    _furOnSource.sharedMaterials = keep;
                }
            }
            _furOnSource = null;
            if (_fur)
            {
                var lg = GetComponent<LODGroup>();
                if (lg)
                {
                    var lods = lg.GetLODs();
                    if (lods.Length > 0)
                    {
                        var rs = new List<Renderer>(lods[0].renderers);
                        if (rs.Remove(_fur)) { lods[0].renderers = rs.ToArray(); lg.SetLODs(lods); }
                    }
                }
                Destroy(_fur.gameObject);
            }
            _fur = null;
            if (_furMesh) Destroy(_furMesh);
            _furMesh = null;
            if (_hasShells) ReleaseShells(_key);
            _hasShells = false;
        }
    }
}
