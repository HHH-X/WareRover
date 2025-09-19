class AGV {
  constructor(id, x, y, size = 1) {
    this.id = id;
    const geometry = new THREE.BoxGeometry(size, 0.5, size);
    const material = new THREE.MeshPhongMaterial({ color: 0xffa500 });
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.position.set(x, 0.25, y);
  }

  update(pos, direction) {
    this.mesh.position.set(pos[0], 0.25, pos[1]);
    this.mesh.rotation.y = THREE.MathUtils.degToRad(direction);
  }
}
export { AGV };
