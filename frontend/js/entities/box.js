import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

class Box {
  constructor(id, logicX, logicY) {
    this.id = id;
    this.logicX = logicX;
    this.logicY = logicY;

    this.mesh = new THREE.Group();
    this.setLogicPosition(logicX, logicY);

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
        console.log('Box loaded', this.id, 'at position', this.logicX, this.logicY);
      },
      undefined,
      (error) => {
        console.error('加载Box模型失败:', error);
      }
    );
  }

  /** 直接设置世界坐标 */
  setXYZ(x, y, z) {
    this.mesh.position.set(x, y, z);
  }

  /** 设置逻辑坐标，自动加偏移映射到世界坐标 */
  setLogicPosition(logicX, logicY) {
    this.logicX = logicX;
    this.logicY = logicY;
    this.mesh.position.set(logicX + 0.5, 0.5, logicY + 0.5);
  }
}

export { Box };
