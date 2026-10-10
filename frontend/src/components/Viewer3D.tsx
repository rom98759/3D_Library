import { useEffect, useRef } from "react";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export default function Viewer3D({ modelId }: { modelId: number }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let rafId = 0;
    let disposed = false;
    const width = container.clientWidth || 300;
    const height = container.clientHeight || 200;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 10000);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    scene.add(new THREE.AmbientLight(0xffffff, 0.7));
    const key = new THREE.DirectionalLight(0xffffff, 0.9);
    key.position.set(1, 1, 1);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.35);
    fill.position.set(-1, -0.5, -1);
    scene.add(fill);

    let controls: OrbitControls | undefined;
    let geometryRef: THREE.BufferGeometry | undefined;
    let materialRef: THREE.Material | undefined;

    new STLLoader().load(
      `/api/models/${modelId}/stl`,
      (geometry) => {
        if (disposed) {
          geometry.dispose();
          return;
        }
        geometryRef = geometry;
        geometry.center();
        geometry.computeBoundingBox();

        const material = new THREE.MeshStandardMaterial({
          color: 0xe9eff3,
          metalness: 0.05,
          roughness: 0.65,
        });
        materialRef = material;
        const mesh = new THREE.Mesh(geometry, material);
        mesh.rotation.x = -Math.PI / 2;
        scene.add(mesh);

        const size = new THREE.Vector3();
        geometry.boundingBox!.getSize(size);
        const maxDim = Math.max(size.x, size.y, size.z) || 1;
        camera.position.set(maxDim * 1.1, maxDim * 0.9, maxDim * 1.4);
        camera.lookAt(0, 0, 0);

        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;

        container.innerHTML = "";
        container.appendChild(renderer.domElement);

        const animate = () => {
          rafId = requestAnimationFrame(animate);
          controls?.update();
          renderer.render(scene, camera);
        };
        animate();
      },
      undefined,
      () => {
        if (!disposed) {
          container.innerHTML =
            '<div class="font-mono text-xs text-bp-red p-2.5">Impossible de charger le rendu 3D</div>';
        }
      }
    );

    return () => {
      disposed = true;
      cancelAnimationFrame(rafId);
      controls?.dispose();
      geometryRef?.dispose();
      materialRef?.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [modelId]);

  return <div ref={containerRef} className="w-full h-full" />;
}
