
class Box {
  constructor(id, x, y, size = 1) {
    this.id = id;
    this.x = x;
    this.y = y;

    const geometry = new THREE.BoxGeometry(size, size, size);
    const material = new THREE.MeshStandardMaterial({ color: 0xffa500 });
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.position.set(x, 0.5, y);
  }
}

export { Box };
