class Shelf {
  constructor(id, x, y) {
    this.id = id;
    const geometry = new THREE.BoxGeometry(1, 2, 1);
    const material = new THREE.MeshPhongMaterial({ color: 0x8b4513 });
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.position.set(x, 1, y);
  }
}
export { Shelf };
