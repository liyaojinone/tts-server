import pytest


class FakeProtector:
    def protect(self, plaintext: bytes) -> bytes:
        return b"encrypted:" + plaintext[::-1]

    def unprotect(self, ciphertext: bytes) -> bytes:
        assert ciphertext.startswith(b"encrypted:")
        return ciphertext.removeprefix(b"encrypted:")[::-1]


def test_token_store_persists_only_encrypted_data_and_exposes_masked_metadata(tmp_path):
    from app.services.huggingface_token import HuggingFaceTokenStore

    path = tmp_path / "secrets" / "huggingface-token.bin"
    store = HuggingFaceTokenStore(path, protector=FakeProtector())

    store.save("hf_example_secret_1234")

    assert path.read_bytes() == b"encrypted:4321_terces_elpmaxe_fh"
    assert b"hf_example_secret_1234" not in path.read_bytes()
    assert store.get() == "hf_example_secret_1234"
    assert store.metadata() == {"configured": True, "token_suffix": "1234"}


def test_token_store_deletes_saved_credential(tmp_path):
    from app.services.huggingface_token import HuggingFaceTokenStore

    path = tmp_path / "secrets" / "huggingface-token.bin"
    store = HuggingFaceTokenStore(path, protector=FakeProtector())
    store.save("hf_example_secret_1234")

    store.delete()

    assert not path.exists()
    assert store.get() is None
    assert store.metadata() == {"configured": False, "token_suffix": None}


@pytest.mark.parametrize("token", ["", "   ", 123])
def test_token_store_rejects_missing_or_non_string_token(tmp_path, token):
    from app.services.huggingface_token import HuggingFaceTokenError, HuggingFaceTokenStore

    store = HuggingFaceTokenStore(tmp_path / "token.bin", protector=FakeProtector())

    with pytest.raises(HuggingFaceTokenError, match="Token"):
        store.save(token)
