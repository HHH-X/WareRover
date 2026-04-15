import * as THREE from 'three';

class Elevator {
  constructor(id, pos, floors, floorHeight) {
    this.id = id;
    this.floors = floors;
    this.floorHeight = floorHeight;
    this.mesh = new THREE.Group();

    const numFloors = floors.length;
    const totalHeight = (numFloors) * floorHeight;
    const minFloor = Math.min(...floors);
    const baseY = minFloor * floorHeight;

    // Shaft frame (wireframe box)
    const shaftGeo = new THREE.BoxGeometry(0.9, totalHeight, 0.9);
    const shaftMat = new THREE.MeshBasicMaterial({
      color: 0xffaa00,
      wireframe: true,
      transparent: true,
      opacity: 0.6
    });
    const shaft = new THREE.Mesh(shaftGeo, shaftMat);
    shaft.position.set(pos[0], baseY + totalHeight / 2, pos[1]);
    this.mesh.add(shaft);

    // Platform (moves between floors)
    const platGeo = new THREE.BoxGeometry(0.8, 0.1, 0.8);
    const platMat = new THREE.MeshStandardMaterial({ color: 0xff8800, metalness: 0.5, roughness: 0.4 });
    this.platform = new THREE.Mesh(platGeo, platMat);
    this.platform.position.set(pos[0], baseY + 0.05, pos[1]);
    this.mesh.add(this.platform);

    // Floor indicator dots
    for (const f of floors) {
      const dotGeo = new THREE.SphereGeometry(0.08, 8, 8);
      const dotMat = new THREE.MeshBasicMaterial({ color: 0xffcc00 });
      const dot = new THREE.Mesh(dotGeo, dotMat);
      dot.position.set(pos[0] + 0.5, f * floorHeight + 0.15, pos[1]);
      this.mesh.add(dot);
    }

    this.pos = pos;
    this.currentY = baseY + 0.05;
  }

  updateState(state, timer) {
    // Could animate platform movement in the future
    if (state === 'TRANSPORTING') {
      this.platform.material.color.setHex(0xff4400);
    } else {
      this.platform.material.color.setHex(0xff8800);
    }
  }
}

export { Elevator };
