"""Evidence-gated company positions over the industry ontology."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
import asyncio
from hashlib import sha256
import json
import multiprocessing
import re
import subprocess
import tempfile
from typing import Iterable

from .contracts import RecordDomain
from .ingestion import FetchRequest
from .official_filings import (
    CNINFO_FILING_DOCUMENT_SOURCE,
    CninfoFilingIndexAdapter,
    OfficialFilingDocumentAdapter,
)


@dataclass(frozen=True)
class CompanyPosition:
    ticker: str
    name: str
    market: str
    segment_id: str
    role: str
    product_keyword: str
    status: str = "needs_evidence"
    citation: tuple[str, int, str] | None = None
    gap_reason: str | None = None


# Self-authored review targets. These are hypotheses, never published facts until
# an official filing yields a page-bound keyword citation at runtime.
REVIEW_TARGETS: tuple[CompanyPosition, ...] = (
    CompanyPosition("688041.SH", "海光信息", "A", "ai-compute/chip-design/cpu", "product developer", "处理器"),
    CompanyPosition("688008.SH", "澜起科技", "A", "ai-compute/chip-design/memory-controller", "product developer", "内存接口"),
    CompanyPosition("688256.SH", "寒武纪", "A", "ai-compute/chip-design/ai-accelerator", "product developer", "智能芯片"),
    CompanyPosition("002371.SZ", "北方华创", "A", "ai-compute/semiconductor-equipment/etch", "equipment supplier", "刻蚀", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-26/1223309278.PDF", 2, "70168364fd518323effa2d11ff337a172783e3597ed6f896353ca62ea3f75cfe")),
    CompanyPosition("688012.SH", "中微公司", "A", "ai-compute/semiconductor-equipment/etch", "equipment supplier", "刻蚀"),
    CompanyPosition("300346.SZ", "南大光电", "A", "ai-compute/semiconductor-materials/photoresist", "materials supplier", "光刻胶", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-03/1222992364.PDF", 2, "fffb100dfbaa79ec476c04b4b8ed62b9ae1271a4cb653e094631a5e28a1db4f8")),
    CompanyPosition("300308.SZ", "中际旭创", "A", "ai-compute/network-optics/optical-module", "component supplier", "光模块", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-21/1223155483.PDF", 6, "1c13639ab218395ef3c81bfbcddb64ba48262d2afcc8ac9ed1588a9dbd4a513f")),
    CompanyPosition("300502.SZ", "新易盛", "A", "ai-compute/network-optics/optical-module", "component supplier", "光模块", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-23/1223219348.PDF", 10, "148155f6d95c86f8f77c6aa5ec7e486e97cea2e9f73c9aaa235079df94140aec")),
    CompanyPosition("300394.SZ", "天孚通信", "A", "ai-compute/network-optics/optical-engine", "component supplier", "光器件", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-21/1223152632.PDF", 3, "b411f1cfbc224f0d12c20a6df89cb0896ffd36b9b2b9f64377a897c2161a2e6c")),
    CompanyPosition("002281.SZ", "光迅科技", "A", "ai-compute/network-optics/optical-module", "component supplier", "光模块", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-24/1223234851.PDF", 10, "a4f57ef8f3787cde4b73bf6547a4bf1011859cba22225b5a2eb5bf3580ac4281")),
    CompanyPosition("002463.SZ", "沪电股份", "A", "ai-compute/compute-systems/pcb", "component supplier", "PCB"),
    CompanyPosition("002916.SZ", "深南电路", "A", "ai-compute/compute-systems/pcb", "component supplier", "PCB"),
    CompanyPosition("603228.SH", "景旺电子", "A", "ai-compute/compute-systems/pcb", "component supplier", "印制电路板", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-29/1223377812.PDF", 4, "5e5a6194be7620356d693fe907a5519ad6c35e242e3e7c444f707dc1d83c798e")),
    CompanyPosition("300476.SZ", "胜宏科技", "A", "ai-compute/compute-systems/pcb", "component supplier", "PCB"),
    CompanyPosition("300124.SZ", "汇川技术", "A", "ai-compute/edge-devices/industrial-ai", "system supplier", "工业自动化"),
    CompanyPosition("002747.SZ", "埃斯顿", "A", "ai-compute/edge-devices/robotics", "system supplier", "工业机器人"),
    CompanyPosition("688165.SH", "埃夫特", "A", "ai-compute/edge-devices/robotics", "system supplier", "工业机器人"),
    CompanyPosition("300750.SZ", "宁德时代", "A", "ai-compute/energy-supply-chain/battery", "energy supplier", "电池", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-03-15/1222806982.PDF", 2, "b4f1713d7b821eb076c102711d177fe942ccc2bc8dd171ae5d7a95799a65b0ad")),
    CompanyPosition("600900.SH", "长江电力", "A", "ai-compute/energy-supply-chain/grid", "energy supplier", "水力发电", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-30/1223421172.PDF", 9, "556767ca1f7c06bb679c827aa6522ff9927d2a63dc2ab64b57194fdc57192048")),
    CompanyPosition("601985.SH", "中国核电", "A", "ai-compute/energy-supply-chain/grid", "energy supplier", "核电", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-29/1223364592.PDF", 1, "051330bc1e62786cab88d9adde07c84be2f819c339f73bd110f32f5e9fbef127")),
    CompanyPosition("601012.SH", "隆基绿能", "A", "ai-compute/energy-supply-chain/renewable", "energy supplier", "光伏", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-05-07/1223477802.PDF", 2, "c9e11fc7ec92a59d7d1ccfcf8a4f1fbb35ee8ec0435df16a3e968497b5f64bb8")),
    CompanyPosition("603019.SH", "中科曙光", "A", "ai-compute/compute-systems/ai-server", "system supplier", "服务器", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-03-05/1222707755.PDF", 12, "321d5b310392069cca025299eec0d071cc1a679decfc1fef067136d707fe7a14")),
    CompanyPosition("000977.SZ", "浪潮信息", "A", "ai-compute/compute-systems/ai-server", "system supplier", "服务器", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-03-29/1222950880.PDF", 10, "c2f5bfe90b96425989a62dadf565b1286b7f6befb36d3e47dcb1df1e38b95429")),
    CompanyPosition("688981.SH", "中芯国际", "A", "ai-compute/manufacturing-packaging/foundry", "manufacturing supplier", "晶圆代工", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-03-28/1222924320.PDF", 12, "d0d08d761acb9c16f88343e313a893be17469d21e96042556378631d069924d1")),
    CompanyPosition("688126.SH", "沪硅产业", "A", "ai-compute/semiconductor-materials/silicon-wafer", "materials supplier", "半导体硅片", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-24/1223237698.PDF", 5, "c46e7ae3fb2596943c090f91c2fcd31e128ddfd53b6934ea4a0ace1933160ee9")),
    CompanyPosition("688111.SH", "金山办公", "A", "ai-compute/ai-software/application-layer", "software supplier", "办公软件", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-03-20/1222847501.PDF", 1, "168fb9dcaaedb27756391912837ddb96098726829305d251a8f8bd64ee908848")),
    CompanyPosition("688787.SH", "海天瑞声", "A", "ai-compute/ai-software/data-engineering", "data supplier", "训练数据", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-26/1223328731.PDF", 5, "edf4cd2642ddfa30ccd3addcce2b3d80f2260cccc492fcf6485f087787fc5991")),
    CompanyPosition("688327.SH", "云从科技", "A", "ai-compute/ai-software/application-layer", "software supplier", "人工智能", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-30/1223424524.PDF", 7, "c788a7628f2e35cf57c8e91ce8a6c299e4dc52221d9a9cc04a1e653ab3e7faa6")),
    CompanyPosition("688343.SH", "云天励飞", "A", "ai-compute/chip-design/ai-accelerator", "product developer", "AI芯片"),
    CompanyPosition("002050.SZ", "三花智控", "A", "ai-compute/power-cooling/heat-exchanger", "component supplier", "热管理", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-03-27/1222913178.PDF", 10, "4f5d1b40f0856c4bcb16a46b7149ef94a1e36e23e7699f180063ca7cc658d763")),
    CompanyPosition("002475.SZ", "立讯精密", "A", "ai-compute/network-optics/interconnect", "component supplier", "连接器"),
    CompanyPosition("000063.SZ", "中兴通讯", "A", "ai-compute/network-optics/switch", "system supplier", "交换机", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-03-01/1222675749.PDF", 18, "05d75561d39aab30d942a8616770e32ad9d14c41aade058025b45f069d9fc2a1")),
    CompanyPosition("688036.SH", "传音控股", "A", "ai-compute/edge-devices/ai-phone", "device supplier", "智能手机", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-24/1223237086.PDF", 6, "dcd23b23e94e2d85747d63754abe8dc1203876d7dc3b1b603190db5a15e2b74d")),
    CompanyPosition("688120.SH", "华海清科", "A", "ai-compute/semiconductor-equipment/clean", "equipment supplier", "清洗", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-29/1223387671.PDF", 9, "1e6a272915b81ff31a3db9bfb5fce2c60af9d953f1d8bc630eea0cef53d991da")),
    CompanyPosition("688037.SH", "芯源微", "A", "ai-compute/semiconductor-equipment/clean", "equipment supplier", "清洗", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-26/1223330378.PDF", 5, "f1825387098e8dffd16b1794803c914738bad24a2844df0753851fe8a5c1274f")),
    CompanyPosition("300054.SZ", "鼎龙股份", "A", "ai-compute/semiconductor-materials/cmp", "materials supplier", "CMP", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-29/1223367500.PDF", 6, "f875d5f589167e24ecd3f50a872317a38023f43c6df942c8483be7c04d9ceb28")),
    CompanyPosition("300661.SZ", "圣邦股份", "A", "ai-compute/energy-supply-chain/power-semiconductor", "product developer", "模拟芯片"),
    CompanyPosition("300418.SZ", "昆仑万维", "A", "ai-compute/ai-software/foundation-model", "software supplier", "人工智能"),
    CompanyPosition("300033.SZ", "同花顺", "A", "ai-compute/ai-software/application-layer", "software supplier", "软件"),
    CompanyPosition("002460.SZ", "赣锋锂业", "A", "ai-compute/energy-supply-chain/battery", "materials supplier", "锂", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-03-29/1222949700.PDF", 1, "74db32844c877e0d88828612f3060108efc504d5a6f2169da3b38198847ae5c9")),
    CompanyPosition("002129.SZ", "TCL中环", "A", "ai-compute/energy-supply-chain/renewable", "materials supplier", "光伏", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-26/1223330188.PDF", 5, "29c34cc8a09d7b941c805839043f2f0ddca89cfd43eae5680f7b7323a98194ec")),
    CompanyPosition("002459.SZ", "晶澳科技", "A", "ai-compute/energy-supply-chain/renewable", "system supplier", "光伏"),
    CompanyPosition("601138.SH", "工业富联", "A", "ai-compute/compute-systems/ai-server", "system supplier", "服务器", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-30/1223421561.PDF", 2, "42d4d1f5c2f7f8daa0931b6f88ba72fbcd2ca8a636c27c524f31b1d85282a00f")),
    CompanyPosition("603986.SH", "兆易创新", "A", "ai-compute/chip-design/memory-controller", "product developer", "存储", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-26/1223305062.PDF", 5, "9653e260a55f639a8ff31ebcf3b2e3bac8116528adcec6c7b50adc739572e353")),
    CompanyPosition("688099.SH", "晶晨股份", "A", "ai-compute/chip-design/ai-accelerator", "product developer", "芯片", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-04-11/1223058176.PDF", 6, "e3a3f654426640ac5691b5af5b6d507b93335e23573bb5e8c635349d3d00822e")),
    CompanyPosition("688123.SH", "聚辰股份", "A", "ai-compute/chip-design/memory-controller", "product developer", "存储"),
    CompanyPosition("688220.SH", "翱捷科技", "A", "ai-compute/chip-design/chip-ip", "product developer", "芯片", "accepted", ("https://static.cninfo.com.cn/finalpage/2025-06-13/1223860108.PDF", 2, "5b21f1bf30cf4e42ffc9e18736af1402fb29960ef8f271a7fc6a6aecc7e2b8d8")),
    CompanyPosition("688521.SH", "芯原股份", "A", "ai-compute/chip-design/chip-ip", "product developer", "IP"),
    CompanyPosition("688498.SH", "源杰科技", "A", "ai-compute/network-optics/optical-engine", "component supplier", "光芯片"),
    CompanyPosition("688047.SH", "龙芯中科", "A", "ai-compute/chip-design/cpu", "product developer", "处理器"),
)


AUDIT_TARGETS = REVIEW_TARGETS


def review_queue() -> tuple[CompanyPosition, ...]:
    return REVIEW_TARGETS


async def audit_position(target: CompanyPosition) -> CompanyPosition:
    """Promote one hypothesis only when an official annual report has a page citation."""

    if target.market != "A":
        return target
    index = CninfoFilingIndexAdapter()
    annual = None
    # CNINFO orders newest-first. Large issuers can have more than one full
    # page of announcements after the annual report, so inspect the bounded
    # H1 result pages rather than treating page one as the whole disclosure set.
    for page in range(1, 5):
        request = FetchRequest.create(
            request_id=f"position-index-{target.ticker}-{page}",
            domain=RecordDomain.EVENT,
            entity_key=target.ticker,
            parameters={
                "start_date": "2025-01-01", "end_date": "2025-06-30", "limit": 50, "page": page,
            },
        )
        index_payload = await index.fetch(request)
        response = json.loads(index_payload.body.decode("utf-8"))
        rows = response.get("announcements") or []
        annual = next(
            (
                row for row in rows
                if "2024年年度报告" in re.sub(r"<[^>]+>", "", str(row.get("announcementTitle") or ""))
                and "摘要" not in str(row.get("announcementTitle") or "")
            ),
            None,
        )
        if annual or not response.get("hasMore"):
            break
    if not annual:
        return target
    document_id = str(annual.get("announcementId") or "")
    adjunct = str(annual.get("adjunctUrl") or "")
    if not document_id or not adjunct:
        return target
    url = "https://static.cninfo.com.cn/" + adjunct.lstrip("/")
    document_request = FetchRequest.create(
        request_id=f"position-document-{target.ticker}",
        domain=RecordDomain.DOCUMENT,
        entity_key=target.ticker,
        parameters={
            "document_id": document_id,
            "document_url": url,
            "title": re.sub(r"<[^>]+>", "", str(annual.get("announcementTitle") or "")),
            "published_at": "2025-01-01T00:00:00Z",
        },
    )
    document = OfficialFilingDocumentAdapter(
        CNINFO_FILING_DOCUMENT_SOURCE, source_url="https://static.cninfo.com.cn/"
    )
    payload = await document.fetch(document_request)
    with tempfile.NamedTemporaryFile(suffix=".pdf") as source:
        source.write(payload.body)
        source.flush()
        extracted = subprocess.run(
            ["pdftotext", "-f", "1", "-l", "500", "-layout", source.name, "-"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    if extracted.returncode:
        raise RuntimeError("official_filing_pdf_text_unavailable")
    page_number = next(
        (index + 1 for index, text in enumerate(extracted.stdout.split("\f")) if target.product_keyword in text),
        None,
    )
    if page_number is None:
        return target
    return replace(target, status="accepted", citation=(payload.source_url, page_number, sha256(payload.body).hexdigest()))


def _audit_worker(target: CompanyPosition, connection: object) -> None:
    try:
        result = asyncio.run(audit_position(target))
        connection.send(("ok", result))  # type: ignore[attr-defined]
    except Exception as exc:
        connection.send(("error", type(exc).__name__))  # type: ignore[attr-defined]
    finally:
        connection.close()  # type: ignore[attr-defined]


def audit_positions(
    targets: Iterable[CompanyPosition] = REVIEW_TARGETS, *, timeout_seconds: float = 18.0
) -> tuple[CompanyPosition, ...]:
    results = []
    for target in targets:
        context = multiprocessing.get_context("fork")
        parent, child = context.Pipe(duplex=False)
        process = context.Process(target=_audit_worker, args=(target, child))
        process.start()
        child.close()
        process.join(timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join()
            results.append(replace(target, gap_reason="official_filing_unavailable:audit_timeout"))
        elif parent.poll():
            status, payload = parent.recv()
            results.append(payload if status == "ok" else replace(target, gap_reason=f"official_filing_unavailable:{payload}"))
        else:
            results.append(replace(target, gap_reason="official_filing_unavailable:worker_exit"))
        parent.close()
    return tuple(results)


def position_coverage(positions: Iterable[CompanyPosition]) -> dict[str, int]:
    rows = tuple(positions)
    return {
        "total": len(rows),
        "accepted": sum(item.status == "accepted" for item in rows),
        "needs_evidence": sum(item.status == "needs_evidence" for item in rows),
        "page_cited": sum(item.citation is not None for item in rows),
        "source_gaps": sum(item.gap_reason is not None for item in rows),
    }
