using System.Reflection;
using UnityEngine;

namespace ThreeDGSAgent
{
    /// <summary>
    /// Runtime sliders for display parameters of the selected splat object
    /// (splat scale, opacity). Uses an on-screen IMGUI panel so no Canvas setup
    /// is needed — just drop it on any GameObject.
    ///
    /// INTEGRATION: this drives the aras-p <c>GaussianSplatRenderer</c> via
    /// reflection, so these scripts compile even before the plugin is installed
    /// and keep working across plugin versions. If your version names the fields
    /// differently, set the member names below in the Inspector — that is the ONLY
    /// version-specific wiring. (Recent versions expose a runtime splat-scale; the
    /// defaults below match the common field names.)
    /// </summary>
    [AddComponentMenu("3DGS-Agent/Display Param UI")]
    public class DisplayParamUI : MonoBehaviour
    {
        [Header("aras-p GaussianSplatRenderer integration (verify names for your version)")]
        [Tooltip("Component type name to drive (matched by Type.Name, namespace ignored).")]
        public string rendererTypeName = "GaussianSplatRenderer";
        [Tooltip("Float field/property for overall splat size.")]
        public string splatScaleMember = "m_SplatScale";
        [Tooltip("Float field/property for opacity/alpha scale. Leave blank if your version has none.")]
        public string opacityMember = "m_OpacityScale";

        [Header("Slider ranges")]
        public float minScale = 0.1f;
        public float maxScale = 2.0f;

        MonoBehaviour _target;     // the GaussianSplatRenderer instance
        float _scale = 1f, _opacity = 1f;
        bool _show = true;

        /// <summary>Rebind the panel to the renderer on the given object (called on selection).</summary>
        public void Bind(GameObject go)
        {
            _target = null;
            foreach (var mb in go.GetComponentsInChildren<MonoBehaviour>())
            {
                if (mb && mb.GetType().Name == rendererTypeName) { _target = mb; break; }
            }
            if (_target != null)
            {
                _scale = ReadFloat(splatScaleMember, 1f);
                _opacity = ReadFloat(opacityMember, 1f);
            }
        }

        void OnGUI()
        {
            if (!_show)
            {
                if (GUI.Button(new Rect(10, 10, 96, 26), "Params ▸")) _show = true;
                return;
            }

            GUILayout.BeginArea(new Rect(10, 10, 270, 160), GUI.skin.box);
            GUILayout.Label(_target ? $"Display · {_target.name}" : "Display · (select an object)");

            GUILayout.Label($"Splat scale: {_scale:0.00}");
            float ns = GUILayout.HorizontalSlider(_scale, minScale, maxScale);
            if (!Mathf.Approximately(ns, _scale)) { _scale = ns; WriteFloat(splatScaleMember, _scale); }

            GUILayout.Label($"Opacity: {_opacity:0.00}");
            float no = GUILayout.HorizontalSlider(_opacity, 0f, 1f);
            if (!Mathf.Approximately(no, _opacity)) { _opacity = no; WriteFloat(opacityMember, _opacity); }

            GUILayout.BeginHorizontal();
            if (GUILayout.Button("Reset"))
            {
                _scale = 1f; _opacity = 1f;
                WriteFloat(splatScaleMember, 1f);
                WriteFloat(opacityMember, 1f);
            }
            if (GUILayout.Button("Hide")) _show = false;
            GUILayout.EndHorizontal();
            GUILayout.EndArea();
        }

        // ---- reflection helpers: read/write a float field or property by name ----
        const BindingFlags Flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;

        float ReadFloat(string member, float fallback)
        {
            if (_target == null || string.IsNullOrEmpty(member)) return fallback;
            var t = _target.GetType();
            var f = t.GetField(member, Flags);
            if (f != null && f.FieldType == typeof(float)) return (float)f.GetValue(_target);
            var p = t.GetProperty(member, Flags);
            if (p != null && p.PropertyType == typeof(float) && p.CanRead) return (float)p.GetValue(_target);
            return fallback;
        }

        void WriteFloat(string member, float value)
        {
            if (_target == null || string.IsNullOrEmpty(member)) return;
            var t = _target.GetType();
            var f = t.GetField(member, Flags);
            if (f != null && f.FieldType == typeof(float)) { f.SetValue(_target, value); return; }
            var p = t.GetProperty(member, Flags);
            if (p != null && p.PropertyType == typeof(float) && p.CanWrite) p.SetValue(_target, value);
        }
    }
}
