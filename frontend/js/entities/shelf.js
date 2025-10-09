import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

class Shelf {
  constructor(id, pos, size) {
    this.id = id;
    this.mesh = new THREE.Group();
    this.mesh.position.set(pos[0], 0, pos[1]); // 直接使用真实坐标

    const loader = new GLTFLoader();
    const SCALE_FACTOR = 1.8;

    loader.load(
      '/frontend/models/shelf.glb',
      (gltf) => {
        const model = gltf.scene;
        model.scale.set(SCALE_FACTOR*size, 2.5, SCALE_FACTOR*size);
        model.position.set(0, 0, 0);

        // 遍历所有 mesh，修改材质为银灰色
        model.traverse((child) => {
          if (child.isMesh) {
            child.material = new THREE.MeshStandardMaterial({
              color: 0xC0C0C0,
              metalness: 0.8,
              roughness: 0.3
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
