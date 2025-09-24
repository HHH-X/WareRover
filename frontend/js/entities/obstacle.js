import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

class Obstacle {
  constructor(logicX, logicY) {
    this.logicX = logicX;
    this.logicY = logicY;

    this.mesh = new THREE.Group();
    this.setLogicPosition(logicX, logicY);

    const loader = new GLTFLoader();
    const SCALE_FACTOR = 1.5; // 你可以根据模型大小调整

    loader.load(
      '/frontend/models/obstacle.glb',
      (gltf) => {
        const model = gltf.scene;
        model.scale.set(SCALE_FACTOR, 2, SCALE_FACTOR);

        // 获取模型包围盒
        const box = new THREE.Box3().setFromObject(model);
        const center = new THREE.Vector3();
        const size = new THREE.Vector3();
        box.getCenter(center);
        box.getSize(size);

        // 先把模型移到原点（中心对齐）
        model.position.sub(center);

        // 再往上抬高一半高度，让底部落在 y=0
        model.position.y += size.y / 2;

        this.mesh.add(model);
        console.log('Obstacle loaded at position', this.logicX, this.logicY);
      },
      undefined,
      (error) => {
        console.error('加载Obstacle模型失败:', error);
      }
    );
  }

  /** 设置逻辑坐标，自动映射到世界坐标 */
  setLogicPosition(logicX, logicY) {
    this.logicX = logicX;
    this.logicY = logicY;
    this.mesh.position.set(logicX + 0.5, 0, logicY + 0.5);
  }
}

export { Obstacle };
