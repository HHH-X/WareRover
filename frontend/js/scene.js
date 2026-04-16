// scene.js
import { AGV } from './entities/agv.js';
import { Shelf } from './entities/shelf.js';
import { Box } from './entities/box.js';
import { Obstacle } from './entities/obstacle.js';
import { RestArea } from './entities/restArea.js';
import { ReceiveArea } from './entities/receiveArea.js';
import { Elevator } from './entities/elevator.js';
import { SafePathRenderer } from './entities/safePathRenderer.js';
import { OrbitControls } from "https://unpkg.com/three@0.112/examples/jsm/controls/OrbitControls.js";
import * as THREE from 'three';
import { CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer.js';

const FLOOR_HEIGHT = 5;

function createScene() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x141319);

  const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
  camera.position.set(25, 15, 20);
  camera.lookAt(15, 0, 15);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  document.getElementById('container').appendChild(renderer.domElement);

  const labelRenderer = new CSS2DRenderer();
  labelRenderer.setSize(window.innerWidth, window.innerHeight);
  labelRenderer.domElement.style.position = 'absolute';
  labelRenderer.domElement.style.top = '0';
  labelRenderer.domElement.style.pointerEvents = 'none';
  document.getElementById('container').appendChild(labelRenderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.screenSpacePanning = false;
  controls.minDistance = 10;
  controls.maxDistance = 150;
  controls.maxPolarAngle = Math.PI / 2;

  const light = new THREE.DirectionalLight(0xffffff, 1);
  light.position.set(10, 30, 10);
  scene.add(light);

  const ambient = new THREE.AmbientLight(0xaaaaaa, 0.5);
  scene.add(ambient);

  const axesHelper = new THREE.AxesHelper(30);
  scene.add(axesHelper);

  const world = {
    scene,
    mapSize: null,
    numFloors: 1,
    floorHeight: FLOOR_HEIGHT,
    floorGroups: new Map(),  // floor_id -> THREE.Group
    agvs: new Map(),
    shelves: new Map(),
    boxes: new Map(),
    obstacles: new Map(),
    restAreas: new Map(),
    receiveAreas: new Map(),
    elevators: new Map(),

    addMap(mapSize, numFloors = 1) {
      this.mapSize = mapSize;
      this.numFloors = numFloors;

      for (let f = 0; f < numFloors; f++) {
        const floorGroup = new THREE.Group();
        floorGroup.position.y = f * FLOOR_HEIGHT;
        this.floorGroups.set(f, floorGroup);

        // Grid lines
        const grid = new THREE.Group();
        const gridMat = new THREE.LineBasicMaterial({
          color: 0xffffff,
          transparent: numFloors > 1,
          opacity: numFloors > 1 ? 0.4 : 1.0
        });

        for (let x = 0; x <= mapSize.width; x++) {
          const pts = [new THREE.Vector3(x, 0.01, 0), new THREE.Vector3(x, 0.01, mapSize.height)];
          grid.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), gridMat));
        }
        for (let z = 0; z <= mapSize.height; z++) {
          const pts = [new THREE.Vector3(0, 0.01, z), new THREE.Vector3(mapSize.width, 0.01, z)];
          grid.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), gridMat));
        }
        floorGroup.add(grid);

        // Floor plane
        const floorColors = [0xaca7fb, 0x8bc8a4, 0xa8c4e0, 0xd4a8d4];
        const floorColor = floorColors[f % floorColors.length];
        const geo = new THREE.PlaneGeometry(mapSize.width, mapSize.height);
        const mat = new THREE.MeshPhongMaterial({
          color: floorColor,
          transparent: f > 0,
          opacity: f > 0 ? 0.7 : 1.0
        });
        const floor = new THREE.Mesh(geo, mat);
        floor.rotation.x = -Math.PI / 2;
        floor.position.set(mapSize.width / 2, 0, mapSize.height / 2);
        floorGroup.add(floor);

        // Floor label
        if (numFloors > 1) {
          const canvas = document.createElement('canvas');
          canvas.width = 128; canvas.height = 64;
          const ctxCanvas = canvas.getContext('2d');
          ctxCanvas.fillStyle = '#ffffff';
          ctxCanvas.font = 'bold 36px sans-serif';
          ctxCanvas.fillText(`F${f}`, 10, 44);
          const texture = new THREE.CanvasTexture(canvas);
          const spriteMat = new THREE.SpriteMaterial({ map: texture });
          const sprite = new THREE.Sprite(spriteMat);
          sprite.scale.set(2, 1, 1);
          sprite.position.set(-1.5, 0.5, -1);
          floorGroup.add(sprite);
        }

        this.scene.add(floorGroup);
      }
    },

    getFloorY(floorId) {
      return (floorId || 0) * FLOOR_HEIGHT;
    },

    addAGV(agv, floorId = 0) {
      agv.floorId = floorId;
      this.agvs.set(agv.id, agv);
      const group = this.floorGroups.get(floorId);
      if (group) group.add(agv.mesh);
      else this.scene.add(agv.mesh);
    },

    addShelf(shelf, floorId = 0) {
      this.shelves.set(`${floorId}_${shelf.id}`, shelf);
      const group = this.floorGroups.get(floorId);
      if (group) group.add(shelf.mesh);
      else this.scene.add(shelf.mesh);
    },

    addBox(box, floorId = 0) {
      box.floorId = floorId;
      this.boxes.set(box.id, box);
      const group = this.floorGroups.get(floorId);
      if (group) group.add(box.mesh);
      else this.scene.add(box.mesh);
    },

    addObstacle(obstacle, floorId = 0) {
      const key = `${floorId}_${obstacle.mesh.position.x},${obstacle.mesh.position.z}`;
      this.obstacles.set(key, obstacle);
      const group = this.floorGroups.get(floorId);
      if (group) group.add(obstacle.mesh);
      else this.scene.add(obstacle.mesh);
    },

    addRestArea(restArea, floorId = 0) {
      const key = `${floorId}_${restArea.mesh.position.x},${restArea.mesh.position.z}`;
      this.restAreas.set(key, restArea);
      const group = this.floorGroups.get(floorId);
      if (group) group.add(restArea.mesh);
      else this.scene.add(restArea.mesh);
    },

    addReceiveArea(receiveArea, floorId = 0) {
      const key = `${floorId}_${receiveArea.mesh.position.x},${receiveArea.mesh.position.z}`;
      this.receiveAreas.set(key, receiveArea);
      const group = this.floorGroups.get(floorId);
      if (group) group.add(receiveArea.mesh);
      else this.scene.add(receiveArea.mesh);
    },

    addElevator(elevator) {
      this.elevators.set(elevator.id, elevator);
      this.scene.add(elevator.mesh);
    },

    setFloorVisibility(floorId, visible) {
      const group = this.floorGroups.get(floorId);
      if (group) group.visible = visible;
    }
  };

  world.safePathRenderer = new SafePathRenderer(scene);

  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    labelRenderer.setSize(window.innerWidth, window.innerHeight);
  });

  window.sceneWorld = world;

  return { scene, camera, renderer, world, controls, labelRenderer };
}

function renderLoop(renderer, labelRenderer, scene, camera, controls) {
  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    if (window.sceneWorld) {
      window.sceneWorld.elevators.forEach(elev => elev.animate());
    }
    renderer.render(scene, camera);
    labelRenderer.render(scene, camera);
  }
  animate();
}

export { createScene, renderLoop, FLOOR_HEIGHT };
