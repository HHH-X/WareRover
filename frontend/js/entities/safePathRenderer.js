// entities/safePathRenderer.js
import * as THREE from 'three';

export class SafePathRenderer {
  constructor(scene) {
    this.scene = scene;
    this.paths = new Map(); // key: agv_id, value: THREE.Line
  }

  updatePaths(safePaths) {
    // 删除前端有但后端没有的路径
    for (const id of this.paths.keys()) {
      if (!(id in safePaths)) {
        const line = this.paths.get(id);
        line.geometry.dispose();
        line.material.dispose();
        this.scene.remove(line);
        this.paths.delete(id);
      }
    }

    // 绘制或更新后端提供的路径
    for (const [agvId, positions] of Object.entries(safePaths)) {
      const points = positions.map(([x, y]) => new THREE.Vector3(x, 0.05, y));
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const material = new THREE.LineBasicMaterial({ color: 0x00ff00 });

      // 如果路径已存在，先清理旧的资源
      if (this.paths.has(agvId)) {
        const oldLine = this.paths.get(agvId);
        oldLine.geometry.dispose();
        oldLine.material.dispose();
        this.scene.remove(oldLine);
      }

      // 添加新的线条
      const line = new THREE.Line(geometry, material);
      this.scene.add(line);
      this.paths.set(agvId, line);
    }
  }
}