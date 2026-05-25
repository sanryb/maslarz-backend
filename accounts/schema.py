from drf_spectacular.extensions import OpenApiAuthenticationExtension


class BearerTokenAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'accounts.authentication.BearerTokenAuthentication'
    name = 'BearerAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
        }
