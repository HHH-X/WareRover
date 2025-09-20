import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
class AGV {
  constructor(id, x, y, size = 0.8, height = 0.3) {
    this.id = id;
    this.size = size;
    this.height = height;
    this.halfHeight = height / 2;
    this.carrying_status = false;

    this.mesh = new THREE.Group(); // 占位，等模型加载后替换
    this.mesh.position.set(x, this.halfHeight, y);

    // 加载 GLB 模型
    const loader = new GLTFLoader();
    const SCALE_FACTOR = 0.035; 
    loader.load('/frontend/models/agv.glb', (gltf) => {
      this.mesh.add(gltf.scene);

      // 缩放模型大小（根据需要调试）
      gltf.scene.scale.set(SCALE_FACTOR, SCALE_FACTOR, SCALE_FACTOR);
      gltf.scene.position.set(0, 0, 0);
    });

    // 创建货物模型（仍然用方块）
    const cargoSize = this.size * 0.8;
    const cargoHeight = this.height * 0.6;
    const cargoGeometry = new THREE.BoxGeometry(cargoSize, cargoHeight, cargoSize);
    const cargoMaterial = new THREE.MeshPhongMaterial({ color: 0x00ff00 });
    this.cargoMesh = new THREE.Mesh(cargoGeometry, cargoMaterial);
    this.cargoMesh.position.set(0, this.height / 2 + cargoHeight / 2, 0);

    this.cargoMesh.visible = false;
    this.mesh.add(this.cargoMesh);
  }

  update(pos) {
    if (Array.isArray(pos) && pos.length >= 2) {
      this.mesh.position.set(pos[0], this.halfHeight, pos[1]);
    }
  }

  setCarryingStatus(status) {
    this.carrying_status = !!status;
    this.cargoMesh.visible = !!status;
  }
}

export { AGV };

