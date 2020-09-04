import tensorflow as tf
from covid19.models._model import Model
from covid19.layers import Rescaling, PEPXBlock
from tensorflow.keras import Input, Sequential
from tensorflow.keras.layers import Layer, Conv2D, BatchNormalization, ReLU, MaxPool2D, Flatten, Dense, add


class _COVIDNetBlock(Layer):
    def __init__(self, channels, n_pepx, **kwargs):
        super().__init__(kwargs)
        self.channels = channels
        self.n_pepx = n_pepx

        self._branch_conv = Sequential([
            Conv2D(channels, 1),
            BatchNormalization(),
            ReLU()
        ])

        self._branch_pepx = []
        for _ in range(n_pepx):
            self._branch_pepx.append(PEPXBlock(channels))

        self._pooling = MaxPool2D(pool_size=(3, 3), strides=(2, 2), padding='same')

    def call(self, inputs, training=None, mask=None):
        branch_conv_output = self._branch_conv(inputs)

        x = inputs
        for i in range(len(self._branch_pepx)):
            x = self._branch_pepx[i](x)
            x = add([x, branch_conv_output])

        return self._pooling(x)

    def get_config(self):
        config = super().get_config()
        config.update({'channels': self.channels, 'n_pepx': self.n_pepx})
        return config


class COVIDNet(Model):
    """
    COVID-19 detection model with specific architecture proposed by Linda Wangg et al. (see docs/COVID-Net).

    Inputs: batches of images with shape (None, 224, 224, 3).
    Outputs: batches of softmax activations (None, 3). The 3 classes are meant to be: covid-19, normal, pneumonia.

    Since the paper does not give all the details, some choices have been taken according to the state of the art:
    - Batch normalization and ReLU activation for every convolutional layer (BN before ReLU).
    - Pooling 3x3 with stride 2 at the end of each block (where the dimensionality decreases in the diagram).
    - Inputs rescaled in the range [-1, 1].
    """

    def __init__(self, name='covidnet', weights='imagenet'):
        super().__init__(name=name)
        self._image_shape = (224, 224, 3)
        self._from_scratch = weights is None

        if weights is not None:
            raise NotImplementedError

        initial_conv = Sequential([
            Conv2D(64, 7, strides=(2, 2), padding='same'),
            BatchNormalization(),
            ReLU()
        ], name='conv_initial')

        self._feature_extractor = Sequential([
            Rescaling(1./127.5, offset=-1),
            initial_conv,
            _COVIDNetBlock(256, 3),
            _COVIDNetBlock(512, 4),
            _COVIDNetBlock(1024, 5),
            _COVIDNetBlock(2048, 3),
        ], name='feature_extractor')

        self._classifier = Sequential([
            Flatten(),
            Dense(1024, activation='relu'),
            Dense(1024, activation='relu'),
            Dense(3, activation='softmax')
        ], name='classifier')

        # required for summary()
        inputs = Input(shape=self.image_shape)
        outputs = self.call(inputs)
        super().__init__(name=name, inputs=inputs, outputs=outputs)
        self.build(input_shape=(None, self.image_shape[0], self.image_shape[1], self.image_shape[2]))

    def call(self, inputs, training=None, mask=None):
        # using Rescaling layer, tf.data.Dataset and tf.keras.Model.fit() causes unknown shape... reshaping fixes
        # see https://gitmemory.com/issue/tensorflow/tensorflow/24520/511633717
        x = tf.reshape(inputs, tf.constant((-1,) + self.image_shape))
        x = self.feature_extractor(x, training=self._from_scratch)      # if pre-trained, BN layers in inference mode
        x = self.classifier(x)
        return x

    @property
    def feature_extractor(self):
        return self._feature_extractor

    @property
    def classifier(self):
        return self._classifier

    @property
    def image_shape(self):
        return self._image_shape