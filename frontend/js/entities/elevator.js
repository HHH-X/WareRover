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
    this.platformOffset = 0.075;

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
    const platGeo = new THREE.BoxGeometry(0.8, 0.15, 0.8);
    this.platIdleMat = new THREE.MeshStandardMaterial({ color: 0xff8800, metalness: 0.5, roughness: 0.4 });
    this.platActiveMat = new THREE.MeshStandardMaterial({ color: 0xff2200, metalness: 0.5, roughness: 0.4 });
    this.platform = new THREE.Mesh(platGeo, this.platIdleMat);
    this.platform.position.set(pos[0], baseY + this.platformOffset, pos[1]);
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
    this.targetY = baseY + this.platformOffset;
    this.lerpSpeed = 0.35;
  }

  updateState(statusData) {
    const state = statusData.state;
    const displayFloor = statusData.display_floor ?? statusData.current_floor;

    if (displayFloor != null) {
      this.targetY = displayFloor * this.floorHeight + this.platformOffset;
    }

    if (state === 'TRANSPORTING' || state === 'MOVING_TO_PICKUP') {
      this.platform.material = this.platActiveMat;
    } else {
      this.platform.material = this.platIdleMat;
    }
  }

  animate() {
    const curY = this.platform.position.y;
    const diff = this.targetY - curY;
    if (Math.abs(diff) > 0.01) {
      this.platform.position.y += diff * this.lerpSpeed;
    } else {
      this.platform.position.y = this.targetY;
    }
  }
}

export { Elevator };
