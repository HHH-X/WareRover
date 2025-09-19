
class Obstacle {
  constructor(x, y, size = 1) {
    const geometry = new THREE.BoxGeometry(size, size, size);
    const material = new THREE.MeshStandardMaterial({ color: 0x333333 });
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.position.set(x, 0.5, y);
  }
}

export { Obstacle };
