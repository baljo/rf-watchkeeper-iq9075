FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git build-essential cmake pkg-config libusb-1.0-0-dev libncurses-dev && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/rtlsdrblog/rtl-sdr-blog.git /src/rtl && cd /src/rtl && git checkout aed0ea19f3a273370a13c9009b96313c75d54c7b && git rev-parse HEAD > /rtl-source.txt && cmake -S . -B build -DINSTALL_UDEV_RULES=OFF -DDETACH_KERNEL_DRIVER=ON && cmake --build build -j4 && cmake --install build && ldconfig
RUN git clone https://github.com/flightaware/dump1090.git /src/dump1090 && cd /src/dump1090 && git checkout 465e06330372ab0586a6a5063c66b60a8750f2b6 && git rev-parse HEAD > /decoder-source.txt && make -j4 dump1090 RTLSDR=yes BLADERF=no HACKRF=no LIMESDR=no SOAPYSDR=no && cp dump1090 /usr/local/bin/dump1090 && /usr/local/bin/dump1090 --help > /decoder-help.txt 2>&1
ENTRYPOINT ["/usr/local/bin/dump1090"]
