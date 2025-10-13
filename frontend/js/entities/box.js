import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js';

class Box {
  constructor(id, pos, size = 1, height = 0.7) {
    this.id = id;

    this.mesh = new THREE.Group();
    this.update(pos, height); // 初始化位置

    const loader = new GLTFLoader();
    const SCALE_FACTOR = 0.05;

    loader.load(
      '/frontend/models/box.glb',
      (gltf) => {
        const model = gltf.scene;
        model.scale.set(SCALE_FACTOR * size, SCALE_FACTOR, SCALE_FACTOR * size);

        // 居中模型
        const box = new THREE.Box3().setFromObject(model);
        const center = new THREE.Vector3();
        box.getCenter(center);
        model.position.sub(center);

        this.mesh.add(model);
      },
      undefined,
      (error) => {
        console.error('加载Box模型失败:', error);
      }
    );

    // === 添加 ID 标签 ===
    const labelDiv = document.createElement('div');
    labelDiv.className = 'box-label';
    labelDiv.textContent = `Box ${id}`;
    labelDiv.style.color = 'yellow';
    labelDiv.style.fontSize = '14px';
    labelDiv.style.fontWeight = 'bold';
    labelDiv.style.textShadow = '1px 1px 2px black';
    labelDiv.style.opacity = '0'; // 初始隐藏

    this.label = new CSS2DObject(labelDiv);
    this.label.position.set(0, height + 0.2, 0); // 放在 Box 上方
    this.mesh.add(this.label);
  }

  update(pos, height = 0.7) {
    this.mesh.position.set(pos[0], height, pos[1]);
    if (this.label) {
      this.label.position.set(0, height + 0.2, 0);
    }
  }

  setLabelVisible(visible) {
    this.label.element.style.opacity = visible ? '1' : '0';
  }
}

export { Box };
