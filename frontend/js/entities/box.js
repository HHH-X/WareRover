import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

class Box {
  constructor(id, x, y) {
    this.id = id;

    this.mesh = new THREE.Group();
    this.setXYZ(x, 0.5, y); // 直接使用真实坐标

    const loader = new GLTFLoader();
    const SCALE_FACTOR = 0.05;

    loader.load(
      '/frontend/models/box.glb',
      (gltf) => {
        const model = gltf.scene;
        model.scale.set(SCALE_FACTOR, SCALE_FACTOR, SCALE_FACTOR);

        // 居中模型
        const box = new THREE.Box3().setFromObject(model);
        const center = new THREE.Vector3();
        box.getCenter(center);
        model.position.sub(center);

        this.mesh.add(model);
      },
      undefined,
      (error) => {
        console.error('加载Box模型失败:', error);
      }
    );
  }

  setXYZ(x, y, z) {
    this.mesh.position.set(x, y, z);
  }
}

export { Box };