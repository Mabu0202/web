from fastapi import Request

def flash(request: Request, message: str, category: str = "success"):
    """
    category: success | info | warning | danger
    """
    store = request.session.get("flash", [])
    store.append({"message": message, "category": category})
    request.session["flash"] = store
