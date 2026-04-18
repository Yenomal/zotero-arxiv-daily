# Zotero arXiv Daily

基于 Zotero 文库的 arXiv 论文推荐与本地归档工具。

## 功能

1. 从 Zotero 文库读取论文摘要作为兴趣语料
2. 使用 `include_path / ignore_path` 选择指定 Zotero collection
3. 从 arXiv RSS 获取最新论文候选
4. 使用 embedding 计算相关性并初排
5. 对候选论文补全文、清洗正文并进行 LLM 评分
6. 将推荐论文写入 Zotero 指定 collection
7. 将 PDF 保存到本地目录
8. 为 Zotero 条目创建本地 linked attachment
9. 写入推荐 note 和阅读 note

## 本地运行

先安装依赖：

```bash
uv sync
```

编辑配置：

```bash
config/base.yaml
```

运行：

```bash
uv run src/zotero_arxiv_daily/main.py
```

或使用本地脚本：

```bash
./run.sh
```

## 核心配置

### Zotero

```yaml
zotero:
  user_id: ???
  api_key: ???
  include_path: ["精读", "精读/**"]
  ignore_path: ["泛读", "泛读/**"]
```

### arXiv

```yaml
source:
  arxiv:
    category: ["cs.AI","cs.CV","cs.LG","cs.CL","cs.RO"]
    include_cross_list: true
```

### 输出

```yaml
output:
  mode: zotero
  zotero:
    collection_path_parts: ["泛读"]
    write_note: true
  pdf:
    enabled: true
    dir: /home/rui/zotero/pdf
```

### LLM 评分

```yaml
scorer:
  enabled: true
  final_top_k: 10
  model: gpt-5.4
```

## 数据流

```text
Zotero 语料
  -> collection 路径过滤
  -> arXiv 候选论文
  -> embedding 初排
  -> 全文补全
  -> 正文清洗
  -> LLM 评分
  -> 二次重排
  -> Zotero 写入
  -> 本地 PDF 保存
```

## 测试

当前测试属于开发辅助内容。若本地保留测试目录，可运行：

```bash
uv run pytest
```

## 说明

当前项目以本地运行作为主要使用方式。本地 PDF 和 Zotero linked attachment 依赖本机文件路径。

## License

AGPLv3。参见 [LICENSE](LICENSE)。
