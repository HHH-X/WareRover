// scene.js
import { AGV } from './entities/agv.js';
import { Shelf } from './entities/shelf.js';
import { Box } from './entities/box.js';
import { Obstacle } from './entities/obstacle.js';
import { RestArea } from './entities/restArea.js';
import { ReceiveArea } from './entities/receiveArea.js';
import { OrbitControls } from "https://unpkg.com/three@0.112/examples/jsm/controls/OrbitControls.js";
// import * as THREE from 'https://unpkg.com/three@0.112/build/three.module.js';
function createScene() {

  // ---------------- 场景 & 渲染器 ----------------
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xf0f0f0);

  const camera = new THREE.PerspectiveCamera(
    75, 
    window.innerWidth / window.innerHeight, 
    0.1, 
    1000
  );
  camera.position.set(25, 8, 20);
  camera.lookAt(15, 0, 15);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(window.innerWidth * 0.7, window.innerHeight);
  document.getElementById('container').appendChild(renderer.domElement);

  // ---------------- OrbitControls ----------------
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; // 平滑控制
  controls.dampingFactor = 0.05;
  controls.screenSpacePanning = false;
  controls.minDistance = 10; // 最小缩放
  controls.maxDistance = 100; // 最大缩放
  controls.maxPolarAngle = Math.PI / 2; // 防止翻转

  // ---------------- 光照 ----------------
  const light = new THREE.DirectionalLight(0xffffff, 1);
  light.position.set(10, 20, 10);
  scene.add(light);

  const ambient = new THREE.AmbientLight(0xaaaaaa, 0.5);
  scene.add(ambient);
  // ---------------- 坐标轴辅助线 ----------------
  const axesHelper = new THREE.AxesHelper(30);
  scene.add(axesHelper);

  // ---------------- 世界容器 ----------------
  const world = {
    scene,
    mapSize: null,

    agvs: new Map(),
    shelves: new Map(),
    boxes: new Map(),
    obstacles: new Map(),
    restAreas: new Map(),
    receiveAreas: new Map(),

    // ---------------- 地图 ----------------
    addMap(mapSize) {
      this.mapSize = mapSize;

      //  自定义网格
      const grid = new THREE.Group();
      const material = new THREE.LineBasicMaterial({ color: 0x888888 });

      // 画竖线
      for (let x = 0; x <= mapSize.width; x++) {
        const points = [
          new THREE.Vector3(x, 0.01, 0), // y=0.01 避免和地板重叠闪烁
          new THREE.Vector3(x, 0.01, mapSize.height)
        ];
        const geometry = new THREE.BufferGeometry().setFromPoints(points);
        const line = new THREE.Line(geometry, material);
        grid.add(line);
      }

      // 画横线
      for (let z = 0; z <= mapSize.height; z++) {
        const points = [
          new THREE.Vector3(0, 0.01, z),
          new THREE.Vector3(mapSize.width, 0.01, z)
        ];
        const geometry = new THREE.BufferGeometry().setFromPoints(points);
        const line = new THREE.Line(geometry, material);
        grid.add(line);
      }

      this.scene.add(grid);

      // 地板
      const geometry = new THREE.PlaneGeometry(mapSize.width, mapSize.height);
      const materialFloor = new THREE.MeshPhongMaterial({ color: 0xeeeeee });
      const floor = new THREE.Mesh(geometry, materialFloor);
      floor.rotation.x = -Math.PI / 2;

      // 平移地板，使左上角在原点
      floor.position.x = mapSize.width / 2;
      floor.position.z = mapSize.height / 2;
      this.scene.add(floor);
    },


    // ---------------- AGV ----------------
    addAGV(agv) {
      this.agvs.set(agv.id, agv);
      this.scene.add(agv.mesh);
    },

    // ---------------- 货架 ----------------
    addShelf(shelf) {
      this.shelves.set(shelf.id, shelf);
      this.scene.add(shelf.mesh);
    },

    // ---------------- 货箱 ----------------
    addBox(box) {
      this.boxes.set(box.id, box);
      this.scene.add(box.mesh);
    },

    // ---------------- 障碍物 ----------------
    addObstacle(obstacle, key = null) {
      const id = key || `${obstacle.mesh.position.x},${obstacle.mesh.position.z}`;
      this.obstacles.set(id, obstacle);
      this.scene.add(obstacle.mesh);
    },

    // ---------------- 休息区 ----------------
    addRestArea(restArea, key = null) {
      const id = key || `${restArea.mesh.position.x},${restArea.mesh.position.z}`;
      this.restAreas.set(id, restArea);
      this.scene.add(restArea.mesh);
    },

    // ---------------- 接收区 ----------------
    addReceiveArea(receiveArea, key = null) {
      const id = key || `${receiveArea.mesh.position.x},${receiveArea.mesh.position.z}`;
      this.receiveAreas.set(id, receiveArea);
      this.scene.add(receiveArea.mesh);
    }
  };

  // ---------------- 窗口自适应 ----------------
  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth * 0.7, window.innerHeight);
  });

  return { scene, camera, renderer, world, controls };
}

function renderLoop(renderer, scene, camera, controls) {
  function animate() {
    requestAnimationFrame(animate);
    controls.update(); 
    renderer.render(scene, camera);
  }
  animate();
}

export { createScene, renderLoop };
