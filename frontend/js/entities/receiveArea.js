import * as THREE from 'three';
import { CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js';

class ReceiveArea {
  constructor(id, pos, size = 1, height = 0.01) {
    this.id = id;

    const geometry = new THREE.PlaneGeometry(size, size);
    const material = new THREE.MeshBasicMaterial({ color: 0xc7f0ec, side: THREE.DoubleSide });
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.rotation.x = -Math.PI / 2;

    // 提升高度，避免与地板重叠
    this.mesh.position.set(pos[0], height, pos[1]);

    // === 添加标签 ===
    const labelDiv = document.createElement('div');
    labelDiv.className = 'recv-label';
    labelDiv.textContent = `Recv ${id}`;
    labelDiv.style.color = 'white';
    labelDiv.style.fontSize = '14px';
    labelDiv.style.fontWeight = 'bold';
    labelDiv.style.textShadow = '1px 1px 2px black';
    labelDiv.style.opacity = '0'; // 初始隐藏

    this.label = new CSS2DObject(labelDiv);
    this.label.position.set(0, height + 0.2, 0);
    this.mesh.add(this.label);
  }

  setLabelVisible(visible) {
    this.label.element.style.opacity = visible ? '1' : '0';
  }
}

export { ReceiveArea };
