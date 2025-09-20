import * as THREE from 'three';
class Box {
  constructor(id, logicX, logicY, size = 0.8) {
    this.id = id;
    this.logicX = logicX; // 保留逻辑坐标，仅用于调试/打印
    this.logicY = logicY;

    const geometry = new THREE.BoxGeometry(size, size, size);
    const material = new THREE.MeshStandardMaterial({ color: 0xffa500 });
    this.mesh = new THREE.Mesh(geometry, material);

    // 直接把逻辑坐标转为渲染坐标
    this.updatePosition(logicX, logicY, size);
  }

  // 每次后端更新时调用
  updatePosition(logicX, logicY, size = 1) {
    this.logicX = logicX;
    this.logicY = logicY;
    this.mesh.position.set(logicX + 0.5, size / 2, logicY + 0.5);
  }
}

export { Box };
