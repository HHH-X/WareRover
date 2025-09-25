import * as THREE from 'three';

class RestArea {
  constructor(x, y, size = 1) {
    const geometry = new THREE.PlaneGeometry(size, size);
    const material = new THREE.MeshBasicMaterial({ color: 0x00ff00, side: THREE.DoubleSide });
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.rotation.x = -Math.PI / 2;

    // 使用真实坐标
    this.updatePosition(x, y);
  }

  updatePosition(x, y) {
    this.mesh.position.set(x, 0.01, y); // 已经是真实坐标
  }
}

export { RestArea };
