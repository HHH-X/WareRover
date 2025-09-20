import * as THREE from 'three';

class Obstacle {
  constructor(logicX, logicY, size = 0.8) {
    this.logicX = logicX; // 保存逻辑坐标
    this.logicY = logicY;

    const geometry = new THREE.BoxGeometry(size, size, size);
    const material = new THREE.MeshStandardMaterial({ color: 0x333333 });
    this.mesh = new THREE.Mesh(geometry, material);

    // 初始化时设置位置
    this.updatePosition(logicX, logicY, size);
  }

  // 更新逻辑 & 渲染位置
  updatePosition(logicX, logicY, size = 1) {
    this.logicX = logicX;
    this.logicY = logicY;
    this.mesh.position.set(logicX + 0.5, size / 2, logicY + 0.5);
  }
}

export { Obstacle };
