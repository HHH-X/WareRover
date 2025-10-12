// entities/safePathRenderer.js
import * as THREE from 'three';

export class SafePathRenderer {
  constructor(scene) {
    this.scene = scene;
    this.paths = new Map(); // key: agv_id, value: THREE.Line
  }

  updatePaths(safePaths) {
    // safePaths: { "agv_id": [[x1, y1], [x2, y2], ...], ... }

    // 1️⃣ 删除前端有但后端没有的路径
    for (const id of this.paths.keys()) {
      if (!(id in safePaths)) {
        const line = this.paths.get(id);
        this.scene.remove(line);
        this.paths.delete(id);
      }
    }

    // 2️⃣ 绘制或更新后端提供的路径
    for (const [agvId, positions] of Object.entries(safePaths)) {
      const points = positions.map(([x, y]) => new THREE.Vector3(x + 0.5, 0.05, y + 0.5));
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const material = new THREE.LineBasicMaterial({ color: 0x00ff00 }); // 绿色安全路径

      // 如果路径已存在，先删掉旧的
      if (this.paths.has(agvId)) {
        const oldLine = this.paths.get(agvId);
        this.scene.remove(oldLine);
      }

      // 创建新的线条对象并添加到场景
      const line = new THREE.Line(geometry, material);
      this.scene.add(line);
      this.paths.set(agvId, line);
    }
  }
}
