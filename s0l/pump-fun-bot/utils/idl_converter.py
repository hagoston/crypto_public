import json
import sys
import os

# Default filenames
THIS_PATH = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT = f"{THIS_PATH}/../idl/idl.json"
DEFAULT_OUTPUT = f"{THIS_PATH}/../idl/raydium_cp_swap_CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C.json"

def convert_idl(idl: dict) -> dict:
    """Convert Anchor 0.30+ IDL JSON to legacy 0.29.x format for AnchorPy."""

    new_idl = idl.copy()

    # Move metadata to root
    if "metadata" in new_idl:
        metadata = new_idl.pop("metadata")
        new_idl.update(metadata)

    # Remove top-level accounts key
    if "accounts" in new_idl:
        del new_idl["accounts"]

    # Convert accounts in instructions
    if "instructions" in new_idl:
        for ix in new_idl["instructions"]:
            if "accounts" in ix:
                for acc in ix["accounts"]:
                    # Convert writable -> isMut
                    if "writable" in acc:
                        acc["isMut"] = acc.pop("writable")
                    else:
                        acc["isMut"] = False
                    # Convert signer -> isSigner
                    if "signer" in acc:
                        acc["isSigner"] = acc.pop("signer")
                    else:
                        acc["isSigner"] = False
                    # Remove other new fields if they exist
                    acc.pop("relations", None)
                    acc.pop("pda", None)
                    acc.pop("address", None)

    # Recursively fix types from "pubkey" to "publicKey"
    def fix_types(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "type" and value == "pubkey":
                    obj[key] = "publicKey"
                elif key == "array" and isinstance(value, list) and value[0] == "pubkey":
                    value[0] = "publicKey"
                else:
                    fix_types(value)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, str) and item == "pubkey":
                    obj[i] = "publicKey"
                else:
                    fix_types(item)

    fix_types(new_idl.get("instructions", []))
    fix_types(new_idl.get("accounts", []))
    fix_types(new_idl.get("types", []))
    fix_types(new_idl.get("events", []))
    fix_types(new_idl.get("errors", []))

    # Merge event fields from types into events
    if "events" in new_idl and "types" in new_idl:
        types_map = {t["name"]: t["type"]["fields"] for t in new_idl["types"] if t.get("type", {}).get("kind") == "struct"}
        for event in new_idl["events"]:
            if event["name"] in types_map:
                event["fields"] = types_map[event["name"]]
                for field in event["fields"]:
                    field["index"] = False

    # Convert unnamed struct fields
    if "types" in new_idl:
        for t in new_idl["types"]:
            if t.get("type", {}).get("kind") == "struct":
                new_fields = []
                if "fields" in t["type"]:
                    for field in t["type"]["fields"]:
                        if isinstance(field, str):
                            new_fields.append({"name": t["name"], "type": field})
                        else:
                            new_fields.append(field)
                    t["type"]["fields"] = new_fields

    # Simplify defined types recursively
    def simplify_defined_types(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "defined" and isinstance(value, dict) and "name" in value:
                    obj[key] = value["name"]
                else:
                    simplify_defined_types(value)
        elif isinstance(obj, list):
            for item in obj:
                simplify_defined_types(item)

    simplify_defined_types(new_idl)

    return new_idl


if __name__ == "__main__":
    # Use command-line args if provided, else default filenames
    infile = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT
    outfile = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT

    with open(infile, "r") as f:
        idl = json.load(f)

    converted = convert_idl(idl)

    with open(outfile, "w") as f:
        json.dump(converted, f, indent=2)

    print(f"Converted IDL saved to {outfile}")
