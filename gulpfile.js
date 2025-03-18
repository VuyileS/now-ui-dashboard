var gulp = require('gulp');
var path = require('path');
var sass = require('gulp-sass')(require('sass')); // Ensure compatibility
var autoprefixer = require('gulp-autoprefixer');
var sourcemaps = require('gulp-sourcemaps');
var open = require('gulp-open');

var Paths = {
  HERE: './',
  DIST: 'dist/',
  CSS: './assets/css/',
  SCSS_TOOLKIT_SOURCES: './assets/scss/now-ui-dashboard.scss',
  SCSS: './assets/scss/**/**'
};

// Compile SCSS
function compileScss() {
  return gulp.src(Paths.SCSS_TOOLKIT_SOURCES)
    .pipe(sourcemaps.init())
    .pipe(sass().on('error', sass.logError))
    .pipe(autoprefixer())
    .pipe(sourcemaps.write(Paths.HERE))
    .pipe(gulp.dest(Paths.CSS));
}

// Watch SCSS changes
function watchFiles() {
  gulp.watch(Paths.SCSS, compileScss);
}

// Open the dashboard
function openDashboard() {
  return gulp.src('examples/dashboard.html')
    .pipe(open());
}

// Define default task
gulp.task('compile-scss', compileScss);
gulp.task('watch', watchFiles);
gulp.task('open', openDashboard);

// Combine tasks
gulp.task('open-app', gulp.series('open', 'watch'));
gulp.task('default', gulp.series('compile-scss', 'watch'));

var browserSync = require('browser-sync').create();

// Serve the dashboard with BrowserSync
function serve() {
  browserSync.init({
    server: {
      baseDir: "./"
    },
    startPath: "examples/dashboard.html", // Set the default start page
    port: 3000 // You can change this if needed
  });

  gulp.watch(Paths.SCSS, gulp.series('compile-scss')).on('change', browserSync.reload);
  gulp.watch("examples/*.html").on('change', browserSync.reload);
}

// Define the new "serve" task
gulp.task('serve', serve);
