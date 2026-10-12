"""解析原生云候选响应，不自行组词或改变排序。"""
import 官方同步探针 as p


def candidates(raw):
    response = p.fields(raw)
    if p.one(p.fields(p.one(response, 1, b'')), 1) != 0:
        raise ValueError('云查询基础状态失败')
    body = p.fields(p.one(response, 5, b''))
    if p.one(body, 1) != 0:
        raise ValueError('云查询业务状态失败')
    rows = []
    for data in body.get(2, []):
        wrapper = p.fields(data)
        candidate = p.fields(p.one(wrapper, 2, b''))
        rows.append({'text': p.one(candidate, 1, b'').decode(),
                     'syllable': p.one(candidate, 3, b'').decode()})
    return rows
