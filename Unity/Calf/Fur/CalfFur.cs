// Optional URP shell fur for the calf's LOD0 body.
// Add to the Calf prefab root (the object with the Animator). At startup it adds one shell material instance per shell.
// Preferred path: the body is the LAST submesh of Calf_LOD0 (the exporter guarantees this), so the shells are appended
// as extra materials and Unity redraws the body submesh once per shell (no mesh copy, deforms with the rig, LOD0 only).
// Fallback: a fur-only copy of the body submesh on a child renderer (needs Read/Write enabled on the model).
// Cost: one extra skinned mesh + `shells` draws of ~47k triangles; use on hero / close-up calves only.
// NOTE: written without a Unity editor in the build environment; verify once in Unity (URP).
using System.Collections.Generic;
using UnityEngine;

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

        SkinnedMeshRenderer _fur;            // fallback child renderer
        SkinnedMeshRenderer _furOnSource;    // preferred path: shells appended to the LOD0 renderer
        int _baseMaterialCount;
        readonly List<Material> _instances = new List<Material>();

        void Start() { Build(); }

        void OnDestroy()
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
            foreach (var m in _instances) if (m) Destroy(m);
            if (_fur && _fur.sharedMesh) Destroy(_fur.sharedMesh);
        }

        public void Build()
        {
            if (furMaterial == null) { Debug.LogWarning("[CalfFur] no fur material assigned", this); return; }
            SkinnedMeshRenderer src = null;
            foreach (var r in GetComponentsInChildren<SkinnedMeshRenderer>(true))
                if (r.name == lod0Name) { src = r; break; }
            if (src == null) { Debug.LogWarning($"[CalfFur] renderer {lod0Name} not found", this); return; }

            Mesh mesh = src.sharedMesh;
            int sub = -1;
            var mats = src.sharedMaterials;
            for (int i = 0; i < mats.Length && i < mesh.subMeshCount; i++)
                if (mats[i] && mats[i].name.StartsWith(bodyMaterialName)) { sub = i; break; }
            if (sub < 0) sub = 0;

            var shellMats = new Material[shells];
            for (int s = 0; s < shells; s++)
            {
                var m = new Material(furMaterial) { name = furMaterial.name + "_Shell" + (s + 1) };
                m.SetFloat("_ShellIndex", s + 1);
                m.SetFloat("_ShellCount", shells);
                m.SetFloat("_FurLength", furLength);
                m.renderQueue = furMaterial.renderQueue + s;     // draw inner shells first
                shellMats[s] = m;
                _instances.Add(m);
            }

            if (sub == mesh.subMeshCount - 1)
            {
                // Preferred path (the exporter puts the body submesh last): a renderer with more materials than submeshes
                // renders the LAST submesh once per extra material -> append the shells; no mesh copy, no extra skinning.
                var all = new List<Material>(mats);
                while (all.Count > mesh.subMeshCount) all.RemoveAt(all.Count - 1);   // idempotent rebuild
                all.AddRange(shellMats);
                src.sharedMaterials = all.ToArray();
                _furOnSource = src;
                _baseMaterialCount = mesh.subMeshCount;
                return;                                           // renderer is already in LOD0 of the LODGroup
            }

            // Fallback: body is not the last submesh -> fur-only copy of the body submesh on a child renderer.
            // Needs Read/Write enabled on the model (Model import settings) to read the vertex data.
            if (!mesh.isReadable) { Debug.LogWarning("[CalfFur] enable Read/Write on the model or export the body as the last submesh", this); return; }
            var fur = new Mesh { name = mesh.name + "_Fur", indexFormat = mesh.indexFormat };
            fur.vertices = mesh.vertices;
            fur.normals = mesh.normals;
            fur.uv = mesh.uv;
            fur.boneWeights = mesh.boneWeights;
            fur.bindposes = mesh.bindposes;
            fur.subMeshCount = 1;
            fur.SetTriangles(mesh.GetTriangles(sub), 0);
            fur.bounds = mesh.bounds;

            var go = new GameObject(lod0Name + "_Fur");
            go.transform.SetParent(src.transform.parent, false);
            go.transform.localPosition = src.transform.localPosition;
            go.transform.localRotation = src.transform.localRotation;
            go.transform.localScale = src.transform.localScale;
            _fur = go.AddComponent<SkinnedMeshRenderer>();
            _fur.sharedMesh = fur;
            _fur.bones = src.bones;
            _fur.rootBone = src.rootBone;
            _fur.localBounds = src.localBounds;
            _fur.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
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
    }
}
