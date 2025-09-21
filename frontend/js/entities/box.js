import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

class Box {
  constructor(id, logicX, logicY ) {
    this.id = id;
    this.logicX = logicX;
    this.logicY = logicY;

    this.mesh = new THREE.Group();
    this.setLogicPosition(logicX, logicY);

    const loader = new GLTFLoader();
    const SCALE_FACTOR = 1 //0.05;
    loader.load(
      '/frontend/models/box.glb',
      (gltf) => {
        const model = gltf.scene;
        model.scale.set(SCALE_FACTOR, SCALE_FACTOR, SCALE_FACTOR);

        const box = new THREE.Box3().setFromObject(model);
        const center = new THREE.Vector3();
        box.getCenter(center);
        model.position.sub(center);

        this.mesh.add(model);
        console.log('Box loaded', this.id, 'at position', this.logicX, this.logicY);

      },
      undefined,
      (error) => {
        console.error('加载Box模型失败:', error);
      }
    );
  }

  setPosition(x, z) {
    this.mesh.position.set(x, 0.5, z);
  }

  setLogicPosition(logicX, logicY) {
    this.logicX = logicX;
    this.logicY = logicY;
    this.mesh.position.set(logicX + 0.5, 0.5, logicY + 0.5);
  }

  attachToAGV(agv) {
    agv.mesh.add(this.mesh);
    this.mesh.position.set(0, agv.height / 2 + 0.5, 0); // 放车顶
  }

  attachToShelf(shelf) {
    shelf.mesh.add(this.mesh);
    this.mesh.position.set(0, 1, 0); // 放到货架顶
  }
}

export { Box };
