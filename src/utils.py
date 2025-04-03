import base64
import hashlib


def as_bytes(data):
    """Helper to ensure that the passed in `data` is encoded as `bytes` or `bytearray`"""
    if isinstance(data, str):
        data = str.encode(data)

    return bytes(data)


def hash_data(data):
    """
    Helper method for computing the hash of the provided file

    `b64` is useful when using the `Content-MD5` header with S3
      https://docs.aws.amazon.com/AmazonS3/latest/API/RESTObjectPUT.html#RESTObjectPUT-requests-request-headers
      https://aws.amazon.com/premiumsupport/knowledge-center/data-integrity-s3/
    """
    # Ensure `data` is a `bytes` object
    data = as_bytes(data)
    h = hashlib.md5(data)

    return dict(
        hex=h.hexdigest(),
        binary=h.digest(),
        b64=base64.b64encode(h.digest()).decode(),
    )
