import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

class Obstacle {
  constructor(pos) {
    this.mesh = new THREE.Group();
    this.mesh.position.set(pos[0], 0, pos[1]);
    const loader = new GLTFLoader();
    const SCALE_FACTOR = 1.5;

    loader.load(
      '/frontend/models/obstacle.glb',
      (gltf) => {
        const model = gltf.scene;
        model.scale.set(SCALE_FACTOR, 2, SCALE_FACTOR);

        const box = new THREE.Box3().setFromObject(model);
        const center = new THREE.Vector3();
        const size = new THREE.Vector3();
        box.getCenter(center);
        box.getSize(size);

        model.position.sub(center);
        model.position.y += size.y / 2;

        this.mesh.add(model);
      },
      undefined,
      (error) => {
        console.error('加载Obstacle模型失败:', error);
      }
    );
  }

}

export { Obstacle };