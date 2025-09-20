class ReceiveArea {
  constructor(logicX, logicY, size = 1) {
    this.logicX = logicX;
    this.logicY = logicY;

    const geometry = new THREE.PlaneGeometry(size, size);
    const material = new THREE.MeshBasicMaterial({ color: 0x0000ff, side: THREE.DoubleSide });
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.rotation.x = -Math.PI / 2;

    // 逻辑坐标 → 渲染坐标（中心点）
    this.updatePosition(logicX, logicY, size);
  }

  updatePosition(logicX, logicY, size = 1) {
    this.logicX = logicX;
    this.logicY = logicY;
    this.mesh.position.set(logicX + size / 2, 0.01, logicY + size / 2);
  }
}

export { ReceiveArea };
