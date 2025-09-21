import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

class Shelf {
  constructor(id, logicX, logicY, modelPath = '/frontend/models/shelf.glb') {
    this.id = id;
    this.logicX = logicX;
    this.logicY = logicY;

    this.mesh = new THREE.Group();
    this.mesh.position.set(logicX + 0.5, 0, logicY + 0.5);

    const loader = new GLTFLoader();
    const SCALE_FACTOR = 1.5;
    loader.load(
      modelPath,
      (gltf) => {
        const model = gltf.scene;
        model.scale.set(SCALE_FACTOR, 2, SCALE_FACTOR);
        model.position.set(0, 0, 0);
        this.mesh.add(model);
      },
      undefined,
      (error) => {
        console.error('加载Shelf模型失败:', error);
      }
    );
  }


}

export { Shelf };
