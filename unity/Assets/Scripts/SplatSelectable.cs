using UnityEngine;

namespace ThreeDGSAgent
{
    /// <summary>
    /// Marks a Gaussian-splat object as pickable. Selection uses a bounds proxy
    /// (a Collider) because splats have no per-triangle geometry to raycast.
    /// Add this + a BoxCollider sized to the splat to each selectable object.
    /// </summary>
    [RequireComponent(typeof(Collider))]
    [AddComponentMenu("3DGS-Agent/Splat Selectable")]
    public class SplatSelectable : MonoBehaviour
    {
        public SplatSceneManager manager;
        public Color highlightColor = new Color(1f, 0.54f, 0.36f); // matches the UI accent

        bool _highlighted;

        void Start()
        {
            if (!manager) manager = FindObjectOfType<SplatSceneManager>();
            if (manager) manager.Register(this);
        }

        void OnDestroy()
        {
            if (manager) manager.Unregister(this);
        }

        /// <summary>World-space bounds of the selection proxy (used to frame the camera).</summary>
        public Bounds WorldBounds
        {
            get
            {
                var c = GetComponent<Collider>();
                return c ? c.bounds : new Bounds(transform.position, Vector3.one);
            }
        }

        public void SetHighlighted(bool on) => _highlighted = on;

        // Visual feedback: outline the bounds while selected. (Cheap and renderer-agnostic.
        // For a stronger effect, drive the splat scale via DisplayParamUI instead.)
        void OnDrawGizmos()
        {
            if (!_highlighted) return;
            Gizmos.color = highlightColor;
            var b = WorldBounds;
            Gizmos.DrawWireCube(b.center, b.size);
        }
    }
}
