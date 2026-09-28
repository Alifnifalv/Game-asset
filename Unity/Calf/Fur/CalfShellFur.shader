// URP shell fur for the calf (one draw per shell; driven by CalfFur.cs which sets _ShellIndex per material instance).
// Shell 0 is the normal Lit body; shells 1.._ShellCount are pushed out along the normal, drooped by gravity and
// alpha-clipped against a strand-noise texture so strands thin toward their tips.
// NOTE: written for URP 12+ (Unity 2021.3+/Unity 6) without a Unity editor in the build environment; verify it compiles once.
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
        Tags { "RenderType" = "TransparentCutout" "Queue" = "AlphaTest+10" "RenderPipeline" = "UniversalPipeline" }

        Pass
        {
            Name "ShellFur"
            Tags { "LightMode" = "UniversalForward" }
            Cull Back
            ZWrite On
            ZTest LEqual

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile_fragment _ _SHADOWS_SOFT
            #pragma multi_compile_fog

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            TEXTURE2D(_BaseMap);  SAMPLER(sampler_BaseMap);
            TEXTURE2D(_FurMask);  SAMPLER(sampler_FurMask);
            TEXTURE2D(_FurNoise); SAMPLER(sampler_FurNoise);

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

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS   : NORMAL;
                float2 uv         : TEXCOORD0;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv         : TEXCOORD0;
                float3 normalWS   : TEXCOORD1;
                float3 positionWS : TEXCOORD2;
                float  h          : TEXCOORD3;
                float  fogCoord   : TEXCOORD4;
            };

            Varyings vert(Attributes v)
            {
                Varyings o;
                float h = saturate(_ShellIndex / max(1.0, _ShellCount));
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
                o.h = h;
                o.fogCoord = ComputeFogFactor(o.positionCS.z);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                half mask = SAMPLE_TEXTURE2D(_FurMask, sampler_FurMask, i.uv).r;
                half strand = SAMPLE_TEXTURE2D(_FurNoise, sampler_FurNoise, i.uv * _StrandDensity).r;
                // no fur where the mask is 0; strands get thinner (fewer texels survive) toward the tip
                clip(mask - 0.02);
                clip(strand - lerp(0.25, 0.25 + _Thinning * 0.75, i.h));

                half3 albedo = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, i.uv).rgb * _BaseColor.rgb;
                albedo *= lerp(1.0 - _RootOcclusion, 1.0, i.h);   // self-shadowing near the skin
                albedo = lerp(albedo, albedo * 1.25 + 0.03, _TipLighten * i.h);

                float3 n = normalize(i.normalWS);
                Light mainLight = GetMainLight(TransformWorldToShadowCoord(i.positionWS));
                half ndl = saturate((dot(n, mainLight.direction) + _Wrap) / (1.0 + _Wrap));
                half3 direct = mainLight.color * (ndl * mainLight.distanceAttenuation * mainLight.shadowAttenuation);
                half3 ambient = SampleSH(n);
                half3 color = albedo * (direct + ambient);
                color = MixFog(color, i.fogCoord);
                return half4(color, 1.0);
            }
            ENDHLSL
        }
    }
    FallBack Off
}
