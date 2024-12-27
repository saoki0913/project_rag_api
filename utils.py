async def check_spo_url(input_url: str) -> str:
    """
    入力されたSPOのURLを想定される形式に修正する。

    Args:
        input_url (str): ユーザーからの入力URL。

    Returns:
        str: 修正されたURL（想定している形式に修正）。
    """
    # 想定しているSPO URLの基本形式
    base_pattern = r"https://intelligentforce0401.sharepoint.com/sites/"
    
    # 入力が想定している形式で始まるかチェック
    if input_url.startswith(base_pattern):
        # 想定以降の文字列を抽出
        remaining_part = input_url[len(base_pattern):]
        
        # プロジェクト名部分だけを抽出（"/"が含まれる場合、それ以降を切り捨てる）
        project_name = remaining_part.split("/")[0]
        
        # 正規化されたURLを返す
        return f"{base_pattern}{project_name}"
    else:
        # 想定外の入力の場合は空文字列やエラーを返す
        return "Invalid SPO URL"