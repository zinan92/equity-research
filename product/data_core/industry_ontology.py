"""Self-owned, versioned AI-compute industry ontology contract."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable


ONTOLOGY_VERSION = "ai-compute-ontology-v1"
SOURCE_STRATEGY = (
    "company filings and announcements; supplier/customer disclosures; "
    "standards bodies and public technical documentation"
)


@dataclass(frozen=True)
class IndustryNode:
    node_id: str
    name: str
    definition: str
    boundary: str


@dataclass(frozen=True)
class IndustrySegment:
    segment_id: str
    node_id: str
    name: str
    definition: str
    boundary: str
    source_strategy: str
    ontology_version: str = ONTOLOGY_VERSION


_NODES: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    ("chip_design", "芯片设计", (("gpu", "通用 GPU"), ("ai_accelerator", "AI 加速器"), ("cpu", "数据中心 CPU"), ("dpu", "数据处理单元 DPU"), ("memory_controller", "存储控制器"), ("network_asic", "网络交换 ASIC"), ("serdes", "高速 SerDes IP"), ("eda", "EDA 工具"), ("chip_ip", "芯片 IP 授权"))),
    ("semiconductor_equipment", "半导体设备", (("lithography", "光刻设备"), ("etch", "刻蚀设备"), ("deposition", "薄膜沉积设备"), ("clean", "清洗设备"), ("metrology", "量测检测设备"), ("ion_implant", "离子注入设备"), ("thermal", "热处理设备"), ("bonding", "键合设备"), ("test_equipment", "晶圆测试设备"))),
    ("semiconductor_materials", "半导体材料", (("silicon_wafer", "硅片"), ("photoresist", "光刻胶"), ("electronic_gas", "电子特气"), ("wet_chemical", "湿电子化学品"), ("target_material", "靶材"), ("cmp", "CMP 材料"), ("mask", "光掩模"), ("packaging_material", "先进封装材料"), ("substrate", "化合物半导体衬底"))),
    ("manufacturing_packaging", "制造与先进封装", (("foundry", "晶圆代工"), ("mature_node", "成熟制程制造"), ("advanced_node", "先进制程制造"), ("memory_fab", "存储制造"), ("osat", "封测服务"), ("2_5d", "2.5D 封装"), ("3d", "3D 堆叠封装"), ("chiplet", "Chiplet 集成"), ("hbm", "高带宽存储封装"))),
    ("compute_systems", "计算系统", (("ai_server", "AI 服务器整机"), ("rack", "机柜集成"), ("motherboard", "服务器主板"), ("pcb", "高速 PCB"), ("ccl", "覆铜板"), ("memory_module", "内存模组"), ("storage_system", "企业级存储"), ("firmware", "服务器固件"), ("system_integration", "系统集成服务"))),
    ("network_optics", "网络与光通信", (("switch", "数据中心交换机"), ("router", "高端路由器"), ("optical_module", "高速光模块"), ("silicon_photonics", "硅光模块"), ("optical_engine", "光引擎"), ("fiber", "光纤光缆"), ("coherent", "相干光通信"), ("network_os", "网络操作系统"), ("interconnect", "高速互连线缆"))),
    ("data_center", "数据中心基础设施", (("colo", "数据中心托管"), ("cloud_region", "云区域"), ("hyperscale", "超大规模集群"), ("cabinet", "机柜与布线"), ("dcim", "数据中心管理软件"), ("site_selection", "选址与园区"), ("construction", "数据中心建设"), ("network_ops", "网络运维"), ("disaster_recovery", "容灾基础设施"))),
    ("power_cooling", "供电与散热", (("ups", "UPS 不间断电源"), ("transformer", "变压器"), ("switchgear", "配电开关设备"), ("power_module", "电源模块"), ("liquid_cooling", "液冷系统"), ("air_cooling", "风冷系统"), ("thermal_material", "导热材料"), ("heat_exchanger", "热交换设备"), ("backup_generation", "备用发电系统"))),
    ("ai_software", "AI 软件与模型", (("foundation_model", "基础模型"), ("model_training", "模型训练平台"), ("inference", "推理服务"), ("mlops", "MLOps 工具"), ("data_engineering", "数据工程"), ("vector_database", "向量数据库"), ("agent_framework", "智能体框架"), ("ai_security", "模型安全"), ("application_layer", "行业 AI 应用"))),
    ("edge_devices", "边缘与终端", (("edge_server", "边缘服务器"), ("ai_pc", "AI PC"), ("ai_phone", "AI 手机"), ("smart_vehicle", "智能汽车计算"), ("robotics", "机器人计算"), ("industrial_ai", "工业 AI 终端"), ("vision", "机器视觉"), ("sensor", "智能传感器"), ("iot_gateway", "物联网网关"))),
    ("security_operations", "安全与运营", (("cybersecurity", "网络安全"), ("identity", "身份与访问管理"), ("data_security", "数据安全"), ("observability", "可观测性"), ("cloud_operations", "云运营"), ("managed_service", "托管服务"), ("compliance", "合规与审计"), ("devops", "DevOps 平台"), ("it_service", "企业 IT 服务"))),
    ("energy_supply_chain", "能源与供应链", (("grid", "电网接入"), ("energy_storage", "储能系统"), ("battery", "数据中心电池"), ("renewable", "可再生能源采购"), ("power_semiconductor", "功率半导体"), ("copper", "铜与导电材料"), ("rare_material", "关键矿产材料"), ("logistics", "设备物流"), ("recycling", "设备回收再利用"))),
)


def _slug(value: str) -> str:
    return value.replace("_", "-")


def build_ontology() -> tuple[tuple[IndustryNode, ...], tuple[IndustrySegment, ...]]:
    nodes: list[IndustryNode] = []
    segments: list[IndustrySegment] = []
    for node_id, node_name, rows in _NODES:
        nodes.append(IndustryNode(node_id, node_name, f"AI compute value-chain domain: {node_name}.", "Includes the named value-chain domain; excludes unclassified adjacent activities."))
        for segment_id, name in rows:
            stable_id = f"ai-compute/{_slug(node_id)}/{_slug(segment_id)}"
            segments.append(IndustrySegment(stable_id, node_id, name, f"A distinct AI-compute value-chain activity for {name}.", f"Includes {name}-specific products or services; excludes the other segments in {node_name}.", SOURCE_STRATEGY))
    validate_ontology(nodes, segments)
    return tuple(nodes), tuple(segments)


def validate_ontology(nodes: Iterable[IndustryNode], segments: Iterable[IndustrySegment]) -> None:
    node_rows, segment_rows = tuple(nodes), tuple(segments)
    if not 10 <= len(node_rows) <= 15:
        raise ValueError("ontology requires 10-15 major nodes")
    if len(segment_rows) < 104:
        raise ValueError("ontology requires at least 104 segments")
    node_ids = [node.node_id for node in node_rows]
    segment_ids = [segment.segment_id for segment in segment_rows]
    if len(node_ids) != len(set(node_ids)) or len(segment_ids) != len(set(segment_ids)):
        raise ValueError("ontology identities must be unique")
    if any(not node.definition or not node.boundary for node in node_rows):
        raise ValueError("every node needs definition and boundary")
    names = [segment.name for segment in segment_rows]
    if len(names) != len(set(names)):
        raise ValueError("segment names must be unique")
    for segment in segment_rows:
        if segment.node_id not in node_ids:
            raise ValueError("segment has orphan node")
        if not all((segment.definition, segment.boundary, segment.source_strategy)):
            raise ValueError("every segment needs definition, boundary and source strategy")
        if segment.ontology_version != ONTOLOGY_VERSION:
            raise ValueError("segment ontology version mismatch")


def ontology_receipt() -> dict[str, object]:
    nodes, segments = build_ontology()
    material = "|".join([*(node.node_id for node in nodes), *(segment.segment_id for segment in segments)])
    return {"schema_version": ONTOLOGY_VERSION, "node_count": len(nodes), "segment_count": len(segments), "identity_hash": sha256(material.encode()).hexdigest(), "source_boundary": "self-authored taxonomy and source strategy only; no archived classification prose, grade or score"}
