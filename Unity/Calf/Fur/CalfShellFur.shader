// URP shell fur for the calf (one draw per shell; driven by CalfFur.cs which sets _ShellIndex per material instance).
// Shell 0 is the normal Lit body; shells 1.._ShellCount are pushed out along the normal, drooped by gravity and
// alpha-clipped against a strand-noise texture so strands thin toward their tips.
// Passes: UniversalForwardOnly (colour; drawn by the Forward, Forward+ and Deferred renderers), DepthOnly (depth prepass,
// depth priming, _CameraDepthTexture) and DepthNormalsOnly (depth-normals prepass for SSAO / decals). All three run the
// same vertex function, so the prepass depth matches the colour pass exactly (depth priming draws with ZTest Equal).
// URP only: the PackageRequirements block makes Built-in / HDRP projects skip this SubShader instead of failing on the
// URP includes (Unity 2021.2+).
// NOTE: written for URP 12+ (Unity 2021.3+ / Unity 6) without a Unity editor in the build environment; the HLSL was
// compiled with DXC against the URP 12 / 14 / 17 ShaderLibrary, but verify it once in Unity.
Shader "Calf/URP/ShellFur"
{
    Properties
    {
        _BaseMap ("Base Color", 2D) = "white" {}
        _BaseColor ("Tint", Color) = (1,1,1,1)
        _FurMask ("Fur Mask (R = length, 0 = no fur)", 2D) = "white" {}
        _FurNoise ("Strand Noise (R)", 2D) = "gray" {}
        _StrandDensity ("Strand Density (tiling)", Float) = 220
        _FurLength ("Fur Length (m)", Float) = 0.009
        _ShellIndex ("Shell Index", Float) = 1
        _ShellCount ("Shell Count", Float) = 12
        _Gravity ("Gravity Droop", Range(0, 2)) = 0.6
        _Thinning ("Strand Thinning", Range(0, 1)) = 0.85
        _RootOcclusion ("Root Occlusion", Range(0, 1)) = 0.55
        _TipLighten ("Tip Lighten", Range(0, 1)) = 0.12
        _Wrap ("Light Wrap", Range(0, 1)) = 0.35
    }

    SubShader
    {
        PackageRequirements { "com.unity.render-pipelines.universal" }
        Tags { "RenderType" = "TransparentCutout" "Queue" = "AlphaTest+10" "RenderPipeline" = "UniversalPipeline" }

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

        TEXTURE2D(_BaseMap);  SAMPLER(sampler_BaseMap);
        TEXTURE2D(_FurMask);  SAMPLER(sampler_FurMask);
        TEXTURE2D(_FurNoise); SAMPLER(sampler_FurNoise);

        // identical in every pass (SRP Batcher)
        CBUFFER_START(UnityPerMaterial)
            float4 _BaseMap_ST;
            half4 _BaseColor;
            float _StrandDensity;
            float _FurLength;
            float _ShellIndex;
            float _ShellCount;
            float _Gravity;
            half _Thinning;
            half _RootOcclusion;
            half _TipLighten;
            half _Wrap;
        CBUFFER_END

        // LOD cross-fade (LODGroup Fade Mode = Cross Fade): the shells fade with the Lit body. URP 14+ (2022.2+) dithers
        // Lit with a dithering texture (LODCrossFade.hlsl); URP 12 has no Lit cross-fade, so use the core hash dither.
        #if defined(LOD_FADE_CROSSFADE)
            #if UNITY_VERSION >= 202220
                #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/LODCrossFade.hlsl"
                #define SHELL_LOD_FADE(positionCS) LODFadeCrossFade(positionCS)
            #else
                #define SHELL_LOD_FADE(positionCS) LODDitheringTransition(uint2(positionCS.xy), unity_LODFade.x)
            #endif
        #else
            #define SHELL_LOD_FADE(positionCS)
        #endif

        struct Attributes
        {
            float4 positionOS : POSITION;
            float3 normalOS   : NORMAL;
            float2 uv         : TEXCOORD0;
            UNITY_VERTEX_INPUT_INSTANCE_ID
        };

        struct Varyings
        {
            float4 positionCS : SV_POSITION;
            float2 uv         : TEXCOORD0;
            float3 normalWS   : TEXCOORD1;
            float3 positionWS : TEXCOORD2;
            float  fogCoord   : TEXCOORD3;
            UNITY_VERTEX_OUTPUT_STEREO
        };

        float ShellHeight() { return saturate(_ShellIndex / max(1.0, _ShellCount)); }

        // shared by every pass: the depth prepass must produce exactly the colour pass's depth
        Varyings ShellVert(Attributes v)
        {
            Varyings o = (Varyings)0;
            UNITY_SETUP_INSTANCE_ID(v);
            UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
            float h = ShellHeight();
            float2 uv = TRANSFORM_TEX(v.uv, _BaseMap);
            float mask = SAMPLE_TEXTURE2D_LOD(_FurMask, sampler_FurMask, uv, 0).r;
            float3 nWS = TransformObjectToWorldNormal(v.normalOS);
            float3 pWS = TransformObjectToWorld(v.positionOS.xyz);
            float len = _FurLength * mask;
            pWS += nWS * (len * h);
            pWS.y -= _Gravity * len * h * h;                 // strands droop toward their tips
            o.positionWS = pWS;
            o.positionCS = TransformWorldToHClip(pWS);
            o.normalWS = nWS;
            o.uv = uv;
            o.fogCoord = ComputeFogFactor(o.positionCS.z);
            return o;
        }

        // LOD fade, then: no fur where the mask is 0; strands get thinner (fewer texels survive) toward the tip
        void ShellClip(Varyings i, float h)
        {
            SHELL_LOD_FADE(i.positionCS);
            half mask = SAMPLE_TEXTURE2D(_FurMask, sampler_FurMask, i.uv).r;
            half strand = SAMPLE_TEXTURE2D(_FurNoise, sampler_FurNoise, i.uv * _StrandDensity).r;
            clip(mask - 0.02);
            clip(strand - lerp(0.25, 0.25 + _Thinning * 0.75, h));
        }
        ENDHLSL

        Pass
        {
            Name "ShellFur"
            // ForwardOnly: this shader has no GBuffer pass, and the Deferred renderer skips plain UniversalForward passes
            Tags { "LightMode" = "UniversalForwardOnly" }
            Cull Back
            ZWrite On
            ZTest LEqual

            HLSLPROGRAM
            #pragma vertex ShellVert
            #pragma fragment frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fragment _ LOD_FADE_CROSSFADE
            #pragma multi_compile_fog

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            half4 frag(Varyings i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                float h = ShellHeight();
                ShellClip(i, h);

                half3 albedo = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, i.uv).rgb * _BaseColor.rgb;
                albedo *= lerp(1.0 - _RootOcclusion, 1.0, h);    // self-shadowing near the skin
                albedo = lerp(albedo, albedo * 1.25 + 0.03, _TipLighten * h);

                float3 n = normalize(i.normalWS);
                #if defined(_MAIN_LIGHT_SHADOWS_SCREEN) && !defined(_SURFACE_TYPE_TRANSPARENT)
                    // URP 12's TransformWorldToShadowCoord has no screen-space case (it returns w = 0)
                    float4 shadowCoord = ComputeScreenPos(TransformWorldToHClip(i.positionWS));
                #else
                    float4 shadowCoord = TransformWorldToShadowCoord(i.positionWS);
                #endif
                Light mainLight = GetMainLight(shadowCoord);
                half ndl = saturate((dot(n, mainLight.direction) + _Wrap) / (1.0 + _Wrap));
                half3 direct = mainLight.color * (ndl * mainLight.distanceAttenuation * mainLight.shadowAttenuation);
                half3 ambient = SampleSH(n);
                half3 color = albedo * (direct + ambient);
                color = MixFog(color, i.fogCoord);
                return half4(color, 1.0);
            }
            ENDHLSL
        }

        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }
            Cull Back
            ZWrite On
            ColorMask R

            HLSLPROGRAM
            #pragma vertex ShellVert
            #pragma fragment DepthFrag
            #pragma multi_compile_fragment _ LOD_FADE_CROSSFADE

            half DepthFrag(Varyings i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                ShellClip(i, ShellHeight());
                return i.positionCS.z;
            }
            ENDHLSL
        }

        Pass
        {
            Name "DepthNormalsOnly"
            Tags { "LightMode" = "DepthNormalsOnly" }
            Cull Back
            ZWrite On

            HLSLPROGRAM
            #pragma vertex ShellVert
            #pragma fragment DepthNormalsFrag
            #pragma multi_compile_fragment _ _GBUFFER_NORMALS_OCT
            #pragma multi_compile_fragment _ LOD_FADE_CROSSFADE

            // same encoding as URP Lit's DepthNormals pass (geometric normal; the shells have no normal map).
            // Rendering layers (_WRITE_RENDERING_LAYERS, decal layers) are not written by the shells.
            half4 DepthNormalsFrag(Varyings i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                ShellClip(i, ShellHeight());
                #if defined(_GBUFFER_NORMALS_OCT)
                    float3 normalWS = normalize(i.normalWS);
                    float2 octNormalWS = PackNormalOctQuadEncode(normalWS);
                    return half4(PackFloat2To888(saturate(octNormalWS * 0.5 + 0.5)), 0.0);
                #else
                    return half4(NormalizeNormalPerPixel(i.normalWS), 0.0);
                #endif
            }
            ENDHLSL
        }
    }
    FallBack Off
}
