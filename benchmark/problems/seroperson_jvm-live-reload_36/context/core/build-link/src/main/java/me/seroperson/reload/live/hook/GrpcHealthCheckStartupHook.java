package me.seroperson.reload.live.hook;

import me.seroperson.reload.live.UnrecoverableException;
import me.seroperson.reload.live.build.BuildLogger;
import me.seroperson.reload.live.settings.DevServerSettings;

/**
 * Startup hook that waits for a GRPC health check to succeed.
 *
 * <p>This hook combines GRPC health checking with startup waiting logic. It polls the GRPC server
 * until it responds, indicating the server has started successfully and is ready to handle
 * requests.
 */
public class GrpcHealthCheckStartupHook implements GrpcHealthCheckHook {

  @Override
  public String description() {
    return "Waits for GRPC health-check to return true";
  }

  @Override
  public boolean isAvailable() {
    return true;
  }

  @Override
  public void hook(Thread th, ClassLoader cl, DevServerSettings settings, BuildLogger logger) {
    try {
      while (true) {
        logger.debug("Waiting for the GRPC health-check to return success ...");
        var service = settings.getGrpcHealthService();
        var healthResponse =
            isHealthy(logger, service, settings.getGrpcHost(), settings.getGrpcPort());
        if (healthResponse == 1) {
          // success
          return;
        } else if (healthResponse == 0) {
          // non-success response, but not an exception
          Thread.sleep(50L);
        } else if (healthResponse == -1) {
          // connection exception
          Thread.sleep(50L);
        } else if (healthResponse == 404) {
          // health-check service isn't implemented
          throw new UnrecoverableException(
              "GRPC health-check service " + service + " is not available. Is it implemented?");
        }
      }
    } catch (InterruptedException e) {
      // Don't print anything, just quit
    }
  }
}
