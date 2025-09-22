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
    const SCALE_FACTOR = 1.8;

    loader.load(
      modelPath,
      (gltf) => {
        const model = gltf.scene;
        model.scale.set(SCALE_FACTOR, 2.5, SCALE_FACTOR);
        model.position.set(0, 0, 0);

        // 遍历所有 mesh，修改材质为银灰色
        model.traverse((child) => {
          if (child.isMesh) {
            // 替换材质为银灰色
            child.material = new THREE.MeshStandardMaterial({
              color: 0xC0C0C0, // 银灰色
              metalness: 0.8,  // 金属感
              roughness: 0.3   // 光滑度
            });
            child.material.needsUpdate = true;
          }
        });

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
