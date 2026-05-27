using UnityEngine;

namespace ThreeDGSAgent
{
    /// <summary>
    /// Browse / zoom / pan camera for inspecting a Gaussian-Splatting scene.
    ///   • Left-drag  : orbit
    ///   • Right/Middle-drag : pan
    ///   • Mouse wheel : zoom
    /// Plugin-agnostic — works with any renderer. Focus is driven by
    /// <see cref="SplatSceneManager"/> via <see cref="Frame"/>.
    /// </summary>
    [RequireComponent(typeof(Camera))]
    [AddComponentMenu("3DGS-Agent/Orbit Camera Controller")]
    public class OrbitCameraController : MonoBehaviour
    {
        [Header("Pivot")]
        public Transform target;                 // optional: object to orbit at start
        public Vector3 targetOffset = Vector3.zero;

        [Header("Speeds")]
        public float orbitSpeed = 4f;
        public float panSpeed = 1f;
        public float zoomSpeed = 4f;

        [Header("Distance limits")]
        public float minDistance = 0.3f;
        public float maxDistance = 80f;

        Vector3 _pivot;
        float _distance = 4f, _yaw, _pitch = 20f;

        void Start()
        {
            _pivot = target ? target.position + targetOffset : transform.position + transform.forward * _distance;
            Vector3 dir = transform.position - _pivot;
            if (dir.sqrMagnitude > 0.0001f)
            {
                _distance = Mathf.Clamp(dir.magnitude, minDistance, maxDistance);
                var e = Quaternion.LookRotation(-dir.normalized).eulerAngles;
                _pitch = e.x > 180f ? e.x - 360f : e.x;
                _yaw = e.y;
            }
            Apply();
        }

        void LateUpdate()
        {
            if (Input.GetMouseButton(0))                       // orbit
            {
                _yaw += Input.GetAxis("Mouse X") * orbitSpeed;
                _pitch = Mathf.Clamp(_pitch - Input.GetAxis("Mouse Y") * orbitSpeed, -89f, 89f);
            }
            if (Input.GetMouseButton(1) || Input.GetMouseButton(2))  // pan
            {
                _pivot += (-transform.right * Input.GetAxis("Mouse X")
                           - transform.up * Input.GetAxis("Mouse Y")) * panSpeed * _distance * 0.1f;
            }
            float scroll = Input.GetAxis("Mouse ScrollWheel");        // zoom
            if (Mathf.Abs(scroll) > 1e-4f)
                _distance = Mathf.Clamp(_distance - scroll * zoomSpeed * _distance, minDistance, maxDistance);

            Apply();
        }

        void Apply()
        {
            Quaternion rot = Quaternion.Euler(_pitch, _yaw, 0f);
            transform.rotation = rot;
            transform.position = _pivot + rot * new Vector3(0f, 0f, -_distance);
        }

        /// <summary>Frame the camera so the given world-space bounds fill the view.</summary>
        public void Frame(Bounds b)
        {
            _pivot = b.center;
            _distance = Mathf.Clamp(b.extents.magnitude * 2.5f + 0.2f, minDistance, maxDistance);
            Apply();
        }
    }
}
