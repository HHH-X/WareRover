import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

class Box {
  constructor(id, logicX, logicY , modelPath = '/frontend/models/box.glb') {
    this.id = id;
    this.logicX = logicX;
    this.logicY = logicY;

    // 占位：避免异步加载前 mesh 为 null
    this.mesh = new THREE.Group();
    this.setLogicPosition(logicX, logicY);

    const loader = new GLTFLoader();
    const SCALE_FACTOR = 0.05; // 根据模型大小调整
    loader.load(
      modelPath,
      (gltf) => {
        const model = gltf.scene;

        // 缩放
        model.scale.set(SCALE_FACTOR, SCALE_FACTOR, SCALE_FACTOR);

        // 计算包围盒
        const box = new THREE.Box3().setFromObject(model);
        const center = new THREE.Vector3();
        box.getCenter(center);

        // 把模型平移，使其中心对齐到 (0,0,0)
        model.position.sub(center);

        // 然后加到 Group 里，Group 就是以后操作的中心
        this.mesh.add(model);
      },
      undefined,
      (error) => {
        console.error('加载Box模型失败:', error);
      }
    );
  }

  // 设置实际渲染位置
  setPosition(x, z) {
    this.mesh.position.set(x, 0.5, z);
  }

  // 设置逻辑位置（带偏移）
  setLogicPosition(logicX, logicY ) {
    this.logicX = logicX;
    this.logicY = logicY;
    this.mesh.position.set(logicX + 0.5, 0.5, logicY + 0.5);
  }
}

export { Box };
