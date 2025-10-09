import * as THREE from 'three';

class ReceiveArea {
  constructor(pos, size = 1) {
    const geometry = new THREE.PlaneGeometry(size, size);
    const material = new THREE.MeshBasicMaterial({ color: 0x0000ff, side: THREE.DoubleSide });
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.rotation.x = -Math.PI / 2;

    // 使用真实坐标
    this.updatePosition(pos[0], pos[1]);
  }

  updatePosition(x, y) {
    this.mesh.position.set(x, 0.01, y); // 已经是真实坐标
  }
}

export { ReceiveArea };
