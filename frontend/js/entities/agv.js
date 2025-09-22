import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

class AGV {
  constructor(id, x, y, size = 0.8, height = 0.3) {
    this.id = id;
    this.size = size;
    this.height = height;
    this.halfHeight = height / 2;

    this.mesh = new THREE.Group();
    this.mesh.position.set(x, this.halfHeight, y);

    const loader = new GLTFLoader();
    const SCALE_FACTOR = 0.027; 
    loader.load('/frontend/models/agv.glb', (gltf) => {
      this.mesh.add(gltf.scene);
      gltf.scene.scale.set(SCALE_FACTOR, SCALE_FACTOR, SCALE_FACTOR);
      gltf.scene.position.set(0, 0, 0);
    });
  }

  update(pos) {
    if (Array.isArray(pos) && pos.length >= 2) {
      this.mesh.position.set(pos[0], 0.08, pos[1]);
    }
  }

}

export { AGV };
