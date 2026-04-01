from django.core.exceptions import ValidationError
from django.db.models.fields.files import ImageFieldFile


def validate_image(
    image: ImageFieldFile,
) -> None:
    file_size = image.file.size
    file_width = image.file.image._size[0]
    file_height = image.file.image._size[1]

    limit_mb = 3  # award image upload cap
    if file_size > limit_mb * 1024 * 1024:
        raise ValidationError(f"Max size of file is {limit_mb} MB")
    elif file_width != file_height:
        raise ValidationError(
            f"File width/height must match. Current: {file_width}x{file_height}"
        )
