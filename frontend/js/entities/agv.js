class AGV {
  /**
   * @param {string|number} id
   * @param {number} x      实际坐标 x（世界坐标）
   * @param {number} y      实际坐标 y（世界坐标）
   * @param {number} size   AGV 在 x/z 平面上的直径
   * @param {number} height AGV 高度
   */
  constructor(id, x, y, size = 0.8, height = 0.3) {
    this.id = id;
    this.size = size;
    this.height = height;
    this.halfHeight = height / 2;

    // 对应后端的状态字段，true=载货, false=不载货
    this.carrying_status = false;

    // AGV 本体（圆柱体）
    const radius = size / 2;
    const geometry = new THREE.CylinderGeometry(radius, radius, height, 32);
    const material = new THREE.MeshPhongMaterial({ color: 0xffa500 });
    this.mesh = new THREE.Mesh(geometry, material);

    // 初始化位置
    this.mesh.position.set(x, this.halfHeight, y);

    // 预先创建货物模型（立方体）
    const cargoSize = this.size * 0.8;
    const cargoHeight = this.height * 0.6;
    const cargoGeometry = new THREE.BoxGeometry(cargoSize, cargoHeight, cargoSize);
    const cargoMaterial = new THREE.MeshPhongMaterial({ color: 0x00ff00 });

    this.cargoMesh = new THREE.Mesh(cargoGeometry, cargoMaterial);
    this.cargoMesh.position.set(0, this.height / 2 + cargoHeight / 2, 0);

    // 初始不显示
    this.cargoMesh.visible = false;
    this.mesh.add(this.cargoMesh);
  }

  /**
   * 更新 AGV 位置
   * pos: [x, y] 或 {x, y} （真实坐标）
   */
  update(pos) {
    if (Array.isArray(pos) && pos.length >= 2) {
      this.mesh.position.set(pos[0], this.halfHeight, pos[1]);
    }
  }

  /**
   * 设置载货状态
   * @param {boolean} status true=载货, false=不载货
   */
  setCarryingStatus(status) {
    this.carrying_status = !!status; // 确保为布尔值
    this.cargoMesh.visible = !!status;
  }
}

export { AGV };
