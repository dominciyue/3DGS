using System.Collections.Generic;
using UnityEngine;

namespace ThreeDGSAgent
{
    /// <summary>
    /// Organises the splat objects in a scene and routes interaction:
    ///   • Left-click (no drag) : select the object under the cursor
    ///   • F   : frame/focus the selected object
    ///   • H   : hide/show the selected object
    ///   • Esc : clear selection
    /// </summary>
    [AddComponentMenu("3DGS-Agent/Splat Scene Manager")]
    public class SplatSceneManager : MonoBehaviour
    {
        public OrbitCameraController orbitCamera;
        public DisplayParamUI displayUI;          // optional: rebinds sliders to the selection
        public float clickDragThreshold = 6f;     // pixels; above this a left-press is an orbit, not a click

        readonly List<SplatSelectable> _objects = new List<SplatSelectable>();
        Vector3 _mouseDown;

        public SplatSelectable Selected { get; private set; }
        public IReadOnlyList<SplatSelectable> Objects => _objects;

        public void Register(SplatSelectable s)
        {
            if (s && !_objects.Contains(s)) _objects.Add(s);
        }

        public void Unregister(SplatSelectable s)
        {
            _objects.Remove(s);
            if (Selected == s) Selected = null;
        }

        public void Select(SplatSelectable s)
        {
            if (Selected) Selected.SetHighlighted(false);
            Selected = s;
            if (s)
            {
                s.SetHighlighted(true);
                if (displayUI) displayUI.Bind(s.gameObject);
            }
            Debug.Log($"[3DGS] selected: {(s ? s.name : "none")}");
        }

        public void FocusSelected()
        {
            if (Selected && orbitCamera) orbitCamera.Frame(Selected.WorldBounds);
        }

        public void ToggleSelectedVisibility()
        {
            if (Selected) Selected.gameObject.SetActive(!Selected.gameObject.activeSelf);
        }

        void Update()
        {
            if (Input.GetMouseButtonDown(0)) _mouseDown = Input.mousePosition;
            if (Input.GetMouseButtonUp(0) &&
                Vector3.Distance(_mouseDown, Input.mousePosition) < clickDragThreshold)
                PickUnderCursor();

            if (Input.GetKeyDown(KeyCode.F)) FocusSelected();
            if (Input.GetKeyDown(KeyCode.H)) ToggleSelectedVisibility();
            if (Input.GetKeyDown(KeyCode.Escape)) Select(null);
        }

        void PickUnderCursor()
        {
            Camera cam = orbitCamera ? orbitCamera.GetComponent<Camera>() : Camera.main;
            if (!cam) return;
            if (Physics.Raycast(cam.ScreenPointToRay(Input.mousePosition), out RaycastHit hit))
            {
                var s = hit.collider.GetComponentInParent<SplatSelectable>();
                if (s) { Select(s); return; }
            }
            Select(null);
        }
    }
}
