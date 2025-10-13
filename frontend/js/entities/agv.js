import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js';

class AGV {
  constructor(id, pos, size = 1, height = 0.3) {
    this.id = id;
    this.size = size;
    this.height = height;
    this.halfHeight = height / 2;

    this.mesh = new THREE.Group();
    this.mesh.position.set(pos[0], this.halfHeight, pos[1]);

    const loader = new GLTFLoader();
    const SCALE_FACTOR = 0.027;
    loader.load('/frontend/models/agv.glb', (gltf) => {
      this.mesh.add(gltf.scene);
      gltf.scene.scale.set(SCALE_FACTOR * size, SCALE_FACTOR, SCALE_FACTOR * size);
      gltf.scene.position.set(0, 0, 0);
    });

    // === 添加 ID 标签 ===
    const labelDiv = document.createElement('div');
    labelDiv.className = 'agv-label';
    labelDiv.textContent = `AGV ${id}`;
    labelDiv.style.color = 'white';
    labelDiv.style.fontSize = '14px';
    labelDiv.style.fontWeight = 'bold';
    labelDiv.style.textShadow = '1px 1px 2px black';
    labelDiv.style.opacity = '0'; // 初始隐藏

    this.label = new CSS2DObject(labelDiv);
    this.label.position.set(0, this.height + 0.2, 0); // 放在AGV上方
    this.mesh.add(this.label);
  }

  update(pos) {
    if (Array.isArray(pos) && pos.length >= 2) {
      this.mesh.position.set(pos[0], 0.06, pos[1]);
    }
  }

  // 显示或隐藏ID
  setLabelVisible(visible) {
    this.label.element.style.opacity = visible ? '1' : '0';
  }
}

export { AGV };
