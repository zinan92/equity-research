// 数据层：fixture 加载与缓存。
// 注意：当前数据源为爱牛归档 2026-07-02 快照（开发 fixture），
// 生产环境必须替换为 N2 canonical API，此文件是唯一接缝。

const cache = new Map();

async function getJSON(path) {
  if (cache.has(path)) return cache.get(path);
  const res = await fetch(path);
  if (!res.ok) throw new Error(`加载失败 ${path}: HTTP ${res.status}`);
  const data = await res.json();
  cache.set(path, data);
  return data;
}

export const api = {
  meta: () => getJSON("fixtures/meta.json"),
  companies: () => getJSON("fixtures/companies.json"),
  chains: () => getJSON("fixtures/chains.json"),
  bubble: () => getJSON("fixtures/bubble.json"),
  catalysts: () => getJSON("fixtures/catalysts.json"),
  levels: () => getJSON("fixtures/levels.json"),
  company: (code) => getJSON(`fixtures/co/${encodeURIComponent(code)}.json`),
};

let indexByCode = null;

export async function companyIndex() {
  if (!indexByCode) {
    const rows = await api.companies();
    indexByCode = new Map(rows.map((r) => [r.code, r]));
  }
  return indexByCode;
}
