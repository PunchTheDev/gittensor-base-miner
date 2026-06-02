import cats.effect.Async
import cats.effect.IO
import cats.effect.IOApp
import cats.effect.Resource
import cats.effect.Sync
import cats.effect.Temporal
import cats.syntax.all._
import com.comcast.ip4s._
import org.http4s._
import org.http4s.dsl.Http4sDsl
import org.http4s.dsl.io._
import org.http4s.ember.server.EmberServerBuilder
import org.http4s.implicits._
import scala.concurrent.duration._

object App extends IOApp.Simple {

  def helloWorldRoutes[F[_]: Sync]: HttpRoutes[F] = {
    val dsl = new Http4sDsl[F] {}
    import dsl._
    HttpRoutes.of[F] {
      case GET -> Root / "greet" =>
        Ok("hello")
      case GET -> Root / "greet2" =>
        Ok("hello")
      case GET -> Root / "health" =>
        Ok()
    }
  }

  def runServer[F[_]: Async]: F[Nothing] = {
    for {
      _ <- Resource.eval(Temporal[F].sleep(2.seconds))
      _ <-
        EmberServerBuilder
          .default[F]
          .withPort(Port.fromInt(me.seroperson.BuildInfo.port).get)
          .withHttpApp(helloWorldRoutes[F].orNotFound)
          .build
    } yield ()
  }.useForever

  val run = runServer[IO]
}